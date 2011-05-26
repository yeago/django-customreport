import copy
from django.db.models.sql.constants import LOOKUP_SEP
from django.db.models import query
from django.db.models.query import QuerySet
from django.db.models import fields

from django_displayset import views as displayset_views

def filter_choice_generator(choices,queryset,filter_fields):
	unfiltered_choices = [f[0] for f in choices]
	indices_to_remove = []
	for x,f in enumerate(unfiltered_choices):
		errors = False

		""" Aggregate Check """
		if isinstance(queryset,QuerySet) and (f in queryset.query.aggregates or f in queryset.query.extra):
			continue # Its directly on the qs already. skip the rest of this error checking

		""" Forward Relation Check """
		model = None
		split_relation = f.split('__')[:-1] # we don't want the field it is accessing, so use [:-1]
		model = queryset.model
		for rel in split_relation:
			# get_field_by_name returns a 4-tuple, 3rd index (2) relates to local fields, 1st index to the field/relation
			field_tuple = model._meta.get_field_by_name(rel)
			# local field on this model
			if field_tuple[2] and (\
					isinstance(field_tuple[0],fields.related.OneToOneField) or \
					isinstance(field_tuple[0],fields.related.ForeignKey)):
				model = field_tuple[0].rel.to
				continue

			# related field on another model
			if not field_tuple[2] and isinstance(field_tuple[0].field,fields.related.OneToOneField):
				model = field_tuple[0].model
				continue

			# if our loop ever reaches this point, that means it failed the above checks and errors MAY be present
			errors = True
			break

		""" Reporting Field Check """
		## 2nd chance: if it exists as a subset query of our filters, then allow it to be displayed, as it won't cause excess queries
		if not [True for filter_field in filter_fields \
					if set(split_relation[:-1]).issubset(set(filter_field.split("__")[:-1]))] and errors:

			indices_to_remove.append(x)

	for offset, index in enumerate(indices_to_remove):
		index -= offset
		del choices[index]

	return choices

def process_queryset(queryset,display_fields=None):
	"""
	This is used in the custom_view below, but its de-coupled so it can be used
	programatically as well. Simply pass in a queryset and a list of relations to display
	and viola.

	Relations look like: ['address__zip','contact__date']
	"""

	display_fields = display_fields or []
	extra_select_kwargs = {}
	select_related = []
	used_routes = []
	distinct = True
	for i in display_fields:
		if i in queryset.query.aggregates or i in queryset.query.extra:
			continue # Want below check to work only for relations, excluding aggregates.

		select_related_token = i
		if LOOKUP_SEP in i:
			"""
			Since select_related() is rather flexible about what it receives
			(ignoring things it doesn't like), we'll just haphazardly pass
			all filter and display fields in for now.
			"""
			select_related_token = i.split(LOOKUP_SEP)
			select_related_token.pop() # get rid of the field name
			select_related_token = LOOKUP_SEP.join(select_related_token)

			"""
			Here we remove distinct status for queries which have reverse relations
			and possibly numerous results per original record
			"""
			if distinct and is_reverse_related(i,queryset.model):
				distinct = False

			primary_model = queryset.model
			join_route = i
			if len(i.split(LOOKUP_SEP)) > 2:
				second_to_last = LOOKUP_SEP.join(i.split(LOOKUP_SEP)[0:-1])
				join_route = LOOKUP_SEP.join(i.split(LOOKUP_SEP)[-2:])
				primary_model = get_closest_relation(queryset.model,second_to_last)[0]

			primary_table = primary_model._meta.db_table
			if primary_table in queryset.query.table_map:
				primary_table = queryset.query.table_map[primary_table][-1] # Will the last one always work?

			join_model, join_field, join_name = get_closest_relation(primary_model,join_route)
			join_table = join_model._meta.db_table

			try:
				join_table = queryset.query.table_map[join_table][-1]
				queryset = queryset.extra(select={i: '%s.%s' % (join_table,join_field.column)})
			except KeyError:
				"""
				Design decision. This will work fine if the ModelAdmin does the displaying of
				related objects for us. At this time, Django doesn't. We have a patch in place
				but aren't using it.

				for now we just need the join column between the primary table and the join table.
				"""

				join_table = join_model._meta.db_table
				join_column = "id" # Always this for now.

				for field_name in primary_model._meta.get_all_field_names():
					from django.db import models
					try:
						field = primary_model._meta.get_field(field_name)
						if (isinstance(field,models.OneToOneField) or isinstance(field,models.ForeignKey)) and \
								field.rel.to == join_model:

							whereclause = '%s.%s=%s.%s' % (join_table,join_column,primary_table,field.column)
							if not join_table in used_routes:
								queryset = queryset.extra(select={i: '%s.%s' % (join_table,join_field.column)},\
										tables=[join_table],where=[whereclause])

							else:
								queryset = queryset.extra(select={i: '%s.%s' % (join_table,join_field.column)},where=[whereclause])

					except models.FieldDoesNotExist:
						pass

				if not join_table in used_routes:
					used_routes.append(join_table)

		if not select_related_token in select_related:
			select_related.append(select_related_token)

	if select_related:
		queryset = queryset.select_related(*select_related)

	if distinct:
		queryset = queryset.distinct()

	return queryset

def is_reverse_related(relation,model):
	from django.db import models
	split_relation = relation.split('__')[:-1] # we don't want the field it is accessing, so use [:-1]
	for rel in split_relation:
		# get_field_by_name returns a 4-tuple, 3rd index (2) relates to local fields, 1st index to the field/relation
		field_tuple = model._meta.get_field_by_name(rel)
		# local field on this model
		if field_tuple[2] and (\
				isinstance(field_tuple[0],models.OneToOneField) or \
				isinstance(field_tuple[0],models.ForeignKey)):
			model = field_tuple[0].rel.to
			continue

		# related field on another model
		if not field_tuple[2] and isinstance(field_tuple[0].field,models.OneToOneField):
			model = field_tuple[0].model
			continue

		return True
	return False

class CustomReportDisplayList(displayset_views.DisplayList):
	def __init__(self,request,*args,**kwargs):
		super(CustomReportDisplayList,self).__init__(request,*args,**kwargs)
		self.list_display.extend(self.get_display_funcs())
		self.order_field, self.order_type = self.get_ordering()
		self.query_set = self.get_query_set()
		self.get_results(request)

	def initial_field_funcs(self):
		def display_field_def(field_name):
			def follow_relations(obj,field_name):
				if getattr(obj,field_name,False):
					return getattr(obj,field_name)

				while "__" in field_name:
					relation, field_name = field_name.split("__",1)
					obj = getattr(obj,relation)

				return getattr(obj,field_name)

			b = lambda obj: follow_relations(obj,field_name)
			b.admin_order_field = field_name
			name = field_name.split("__")
			if len(name) > 1:
				name = ' '.join(name[-2:])
			else:
				name = name[0]

			b.short_description = name
			return b

		### The function below returns another function, which is used to grab from the result a specific attribute name.
		## These function returned are the same as the function that would be set in the above class CustomReportDisplaySet
		## for list_display
		custom_report_defs = [(f, display_field_def(f)) for f in self.model_admin.display_fields if not callable(f)]

		# We then take the list of functions, along with their field names, and append them as attributes on this class
		# which get called later for each result
		for attr_name,definition in custom_report_defs:
			setattr(self.model_admin,attr_name,definition)

		return [string_repr[0] for string_repr in custom_report_defs]

	""" hook for setting the links header name """
	def get_link_description(self):
		return ''

	def get_link_order(self):
		return None

	def get_link_func(self):
		description = self.get_link_description()
		if not description: # honestly, if we don't have a description header, no reason to continue
			return "no 'get_link_description' set"

		def link_name(record):
			return "<a href='%s'>%s</a>" % (record.get_absolute_url(), record)
		link_name.admin_order_field = self.get_link_order()
		link_name.allow_tags = True
		link_name.short_description = description
		return link_name

	def get_display_funcs(self):
		list_display = self.initial_field_funcs()
		if self.model_admin.auto_link:
			list_display.insert(0, self.get_link_func())
		return list_display

class CustomReportDisplaySet(displayset_views.DisplaySet):
	list_display = []
	display_fields = []
	custom_display_fields = []
	auto_link = False
	change_list_template = 'customreport/base.html'

	def get_changelist(self,request):
		CustomReportDisplayList.filtered_queryset = self.filtered_queryset
		return CustomReportDisplayList

def display_list(query_class,_model_class=None,inclusions=None,exclusions=None,depth=None,\
		model_exclusions=None,_max_depth=None,_relation_list=None):
	"""
	User Args:
		depth: how far our relation follows, we want to make sure to include forward then backward relations, as well.
			ex. depth=1, consumer->field, consumer->disability_primary->field, consumer->address->field, consumer<-goal<-field, consumer<-pwi<-field

		inclusions: A list of string-module relationships we want to be allowed to choose from, if not passed in, it means we want all the relations

		exclusions: A list of string-module relationships to not follow, it could be a field or whole relation.

		query_class: The class at the top of the tree hierarchy, essentially what we are reporting on.

	Function Args:
		_model_class: As we progress through the tree, we need to keep track of what model we are on.

		_max_depth: Takes the depth, and depth starts as a counter from 0, just easier to read this way

		_relation_list: What our function returns, but we need to pass it through so it can find it's way to the top... may be able to change this though

	function return: A list of tuples, where each tuple represents (string-module relationship, human-readable-value)
		ex. [
				('first_name', 'Consumer :: First Name'),
				('address__zip',	'Consmer :: Address :: Zip'),
				('pwi__refer_date', 'Consumer :: PWI :: Referral Date')
			]
	"""
	_relation_list = _relation_list or []
	exclusions = exclusions or []
	model_exclusions = model_exclusions or []
	inclusions = inclusions or []

	# if no model class is passed, then we are at the beginning or "base_class"
	query_aggregates = None
	if query_class.__class__ == query.QuerySet:
		query_aggregates = query_class.query.aggregates
		query_class = query_class.model

	_model_class = _model_class or query_class

	## less typing when calling the function, we use depth to set _max_depth from the first call, and use _max_depth henceforth.
	# thus depth just keeps track of what level we are on
	if not _max_depth:
		_max_depth = depth
		depth = 0

	exclusions.extend(['logentry', 'message', 'id']) # these are always excluded fields

	## We dont want our backward relations in the next recursive step, so we add it to our exclusions.
	# as well as the base class.
	exclusions.append(_model_class._meta.module_name)
	model_exclusions.append(_model_class._meta.module_name)

	current_inclusions = [r.split(LOOKUP_SEP,1)[0] for r in inclusions] # these are the ONLY fields and relations to be returned
	current_exclusions = [r for r in exclusions if LOOKUP_SEP not in r] # these are the fields / relations we don't want to show up


	# Non-relational fields are easy and just get appended to the list as is pretty much
	non_relation_fields = [f for f in _model_class._meta.fields if \
			f.name not in current_exclusions and
			f.name not in model_exclusions]

	# Now handle the relations
	# Get the forward ones
	relations = [(f.rel.to, f.name, f.verbose_name.lower()) for f in _model_class._meta.fields if \
			hasattr(f.rel, "to") and \
			f.name not in current_exclusions and
			f.rel.to._meta.module_name not in model_exclusions]

	# and grab our backward ones
	relations.extend([(r.model, r.field.related_query_name(), r.model._meta.verbose_name) for r in _model_class._meta.get_all_related_objects() if \
			r.model._meta.module_name not in current_exclusions and
			r.model._meta.module_name not in model_exclusions])

	# We have to handle the inclusion list separately because if there isn't one, we don't want to filter over nothing
	if current_inclusions:
		non_relation_fields = [f for f in non_relation_fields if f.name in current_inclusions]
		relations = [r for r in relations if r[0]._meta.module_name in current_inclusions] # r == (model, model.verbose_name)

	# At this point we are finally adding our fields to the tuple list
	if query_aggregates:
		[_relation_list.append(( q, q )) for q in query_aggregates.keys()]

	for field in non_relation_fields:
		if _model_class != query_class:
			_relation_list.append((
				field.name,
				field.verbose_name.lower()
				#' :: '.join([_model_class._meta.verbose_name.lower(), field.verbose_name.lower()])
			))
		else: _relation_list.append(( field.name, ' :: '.join([_model_class._meta.module_name, field.verbose_name.lower()]) ))

	## Recursion happens at this point, we are basically going down one tree / relations at a time before we do another one
	# so taking consumer... it will do consumer->address->zip and then it will do consumer->emergency_contact and
	# then whatever backward relations
	for relation in relations:
		# prepare the inclusion/exclusion for the next recursive call by chopping off all relations that match the one in our loop
		relation_inclusions = [name.split(LOOKUP_SEP, 1)[1] for name in inclusions if LOOKUP_SEP in name and name.split(LOOKUP_SEP,1)[0] == relation[1]]
		relation_exclusions = [name.split(LOOKUP_SEP, 1)[1] for name in exclusions if LOOKUP_SEP in name and name.split(LOOKUP_SEP,1)[0] == relation[1]]

		if current_inclusions: pass # if we have inclusions we want to continue with, don't return this tree yet
		elif depth >= _max_depth: return _relation_list # return this tree

		# if we have reached a star in the exclusions, then skip the rest of this relation
		if [True for r in relation_exclusions if '*' in r.split(LOOKUP_SEP, 1)[0]]:
			continue

		# recurse
		###
		# we use copy.deepcopy on model_exclusions because we don't want a global list of exclusions everytime it adds a new one,
		# just the ones down this tree
		relation_pair_list = display_list(query_class,_model_class=relation[0],\
			inclusions=relation_inclusions,exclusions=relation_exclusions,model_exclusions=copy.deepcopy(model_exclusions),\
			depth=depth + 1,_max_depth=_max_depth)

		# build the module-relation and human-readable string
		###
		# We check if _model_class != query_class because we have a case here where once we hit the top of the tree,
		# then we don't want to append the query_class to the module-relation
		if _model_class != query_class:
			_relation_list.extend([
				(LOOKUP_SEP.join([relation[1], relation_pair[0]]),
				' :: '.join([relation[2], relation_pair[1]]))
				for relation_pair in relation_pair_list
			])
		else:
			_relation_list.extend([
				(LOOKUP_SEP.join([relation[1], relation_pair[0]]),
				' :: '.join([_model_class._meta.module_name, relation[2], relation_pair[1]])) \
				for relation_pair in relation_pair_list
			])

	# go back up the recursion tree now
	return _relation_list

def get_closest_relation(model,relation,parent=None):
	if not LOOKUP_SEP in relation:
		if hasattr(model,'base') and relation in model.base.field.rel.to._meta.get_all_field_names():
			"""
			If this model has a base class and the field is really on it,
			return the actual base class. They can always explicitly get the
			subclass.
			"""
			model = model.base.field.rel.to

		return model, model._meta.get_field_by_name(relation)[0], model._meta.module_name

	this_module = relation.split(LOOKUP_SEP,1)

	for rel in model._meta.get_all_related_objects():
		if this_module[0] in [rel.var_name,rel.get_accessor_name()]:
			return get_closest_relation(rel.model,this_module[1],parent=model)

	if this_module[0] in model._meta.get_all_field_names():
		return get_closest_relation(model._meta.get_field_by_name(this_module[0])[0].rel.to,this_module[1],parent=model)

def get_querystring_route(model,relation,parent=None,route=None):
	route = route or []
	if not LOOKUP_SEP in relation:
		route.append(relation)
		return "__".join(route)

	this_module = relation.split(LOOKUP_SEP,1)
	for rel in model._meta.get_all_related_objects():
		if this_module[0] in [rel.var_name,rel.get_accessor_name()]:
			route.append(rel.field.related_query_name())

			return get_querystring_route(rel.model,this_module[1],parent=model,route=route)

	if this_module[0] in model._meta.get_all_field_names():
		das_rel = model._meta.get_field_by_name(this_module[0])[0].rel
		route.append(this_module[0])
		return get_querystring_route(das_rel.to,this_module[1],parent=model,route=route)
