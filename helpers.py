import copy
from django.db.models.sql.constants import LOOKUP_SEP
from django.db.models import query
from django_displayset import views as displayset_views

class CustomReportDisplaySet(displayset_views.DisplaySet):
	list_display = []
	change_list_template = 'customreport/base.html'
	def __init__(self,*args,**kwargs):
		self.list_display = self.get_display_funcs()
		super(CustomReportDisplaySet,self).__init__(*args,**kwargs)

	def initial_field_funcs(self):
		def display_field_def(field_name):	
			b = lambda obj: getattr(obj,field_name)
			name = field_name.split("__")
			if len(name) > 1:
				name = ' '.join(name[-2:])
			else: name = name[0]
			b.short_description = name
			return b

		### The function below returns another function, which is used to grab from the result a specific attribute name.
		## These function returned are the same as the function that would be set in the above class CustomReportDisplaySet
		## for list_display												
		custom_report_defs = [(f, display_field_def(f)) for f in self.display_fields if not callable(f)]

		## To allow the fields to be ordered, we have to set each definition with an attribute called admin_order_field
		## as the django docs suggest
		for name,definition in custom_report_defs:
			definition.admin_order_field = name
																					
		# We then take the list of functions, along with their field names, and append them as attributes on this class
		# which get called later for each result
		for attr_name,definition in custom_report_defs:
			setattr(self,attr_name,definition)

		return [string_repr[0] for string_repr in custom_report_defs]
	
	""" hook for setting the links header name """
	def get_link_description(self):
		return 'Link'
	
	def get_link_order(self):
		return None

	def get_link_func(self):
		description = self.get_link_description()
		if not description: # honestly, if we don't have a description header, no reason to continue
			return None

		def link_name(record):
			return "<a href='%s'>%s</a>" % (record.get_absolute_url(), record) 
		link_name.admin_order_field = self.get_link_order()
		link_name.allow_tags = True
		link_name.short_description = description
		return link_name
	
	def get_display_funcs(self):
		list_display = self.initial_field_funcs()
		if self.get_link_func():
			list_display.insert(0, self.get_link_func())
		return list_display
		
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

	non_relation_fields = [f for f in _model_class._meta.fields if \
			f.name not in current_exclusions and 
			f.name not in model_exclusions]
	# We get our forward relations first...
	relations = [(f.rel.to, f.name, f.verbose_name.lower()) for f in _model_class._meta.fields if \
			hasattr(f.rel, "to") and \
			f.name not in current_exclusions and
			f.rel.to._meta.module_name not in model_exclusions
	]
	### ...and extend it with our backward relations
	relations.extend([(r.model, r.field.related_query_name(), r.model._meta.verbose_name) for r in _model_class._meta.get_all_related_objects() if \
			r.model._meta.module_name not in current_exclusions and
			r.model._meta.module_name not in model_exclusions
	])
	
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
