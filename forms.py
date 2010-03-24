import copy
from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.db.models import fields
from django.db.models.query import QuerySet

class BaseCustomPreForm(forms.Form):
	def __init__(self,*args,**kwargs):
		self.queryset = kwargs.pop('queryset')
		super(BaseCustomPreForm,self).__init__(*args,**kwargs)

class CustomPreFormValidation(BaseCustomPreForm):
	def clean(self):
		"""
		Extra Validation:
			1. check if the display field exists on the primary model / aggregates
			2. check if the display field is a forward relation all the way
			3. check if the display field relation exists in the reporting fields
				if any of these fail, raise a validation error.
		"""	
		if self.cleaned_data.get('display_fields') and self.cleaned_data.get('filter_fields'):
			for f in self.cleaned_data.get('display_fields'):
				"""
				If they wish to display a field on a related model without filtering on that model,
				we must stop them. At all costs.
				"""
	
				errors = False

				""" Aggregate Check """
				if isinstance(self.queryset,QuerySet) and (f in self.queryset.query.aggregates or f in self.queryset.query.extra):
					continue # Its directly on the qs already. skip the rest of this error checking

				""" Forward Relation Check """
				model = None	
				split_relation = f.split('__')[:-1] # we don't want the field it is accessing, so use [:-1]
				model = self.queryset.model
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
					#raise forms.ValidationError("Many %ss are linked from %s. Please filter on %s." % (rel, model._meta.verbose_name, rel))

				""" Reporting Field Check """	
				## 2nd chance: if it exists as a subset query of our filters, then allow it to be displayed, as it won't cause excess queries
				if not [True for filter_field in self.cleaned_data.get('filter_fields') \
							if set(split_relation).issubset(set(filter_field.split("__")[:-1]))] and errors:

					filtering_field = f.split('__')[0]
					if len(f.split('__')) > 1:
						filtering_field = f.split('__')[-2] # we want the last module, not the field

					raise forms.ValidationError("Cannot display the field '%s' without also filtering on %s." \
							% (' :: '.join(f.split('__')),filtering_field) )

		return self.cleaned_data

def filter_choices(choices,queryset,filter_fields):
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
					if set(split_relation).issubset(set(filter_field.split("__")[:-1]))] and errors:

			indices_to_remove.append(x)

	for offset, index in enumerate(indices_to_remove):
		index -= offset
		del choices[index]

	return choices
	

class RelationMultipleChoiceField(forms.MultipleChoiceField):
	def __init__(self,queryset,depth=3,inclusions=None,exclusions=None,filter_fields=None,*args,**kwargs):
		from django_customreport.helpers import display_list
		filter_fields = filter_fields or []
		unfiltered_choices = display_list(queryset,depth=depth,inclusions=inclusions,exclusions=exclusions)
		choices = filter_choices(unfiltered_choices,queryset,filter_fields)

		kwargs.update({
			'choices': choices,
			'widget': FilteredSelectMultiple("display_fields", is_stacked=False)
		})
		super(RelationMultipleChoiceField,self).__init__(*args,**kwargs)

class FilterSetCustomPreForm(BaseCustomPreForm): # Convenience PreForm which accepts a django-filters filterset
	def __init__(self,filter,data,exclusions=None,inclusions=None,depth=None,queryset=None):
		self._filter = filter
		self._exclusions = exclusions
		self._inclusions = inclusions
		self._depth = depth
		if not isinstance(queryset,QuerySet):
			queryset = filter.queryset

		super(FilterSetCustomPreForm,self).__init__(data,queryset=queryset)
		self.update_field_labels() # Separated in case __init__ work wants to change these labels.

	def update_field_labels(self):
		filter_choices = []
		for field in self._filter.base_filters.keys():
			value = field
			if '__' in field:
				value = ' :: '.join(field.split('__')[-2:])
			value = ' '.join(value.split('_'))
			filter_choices.append((field,value.title()))

		import operator
		filter_choices = sorted(filter_choices, key=operator.itemgetter(1))

		self.fields['filter_fields'] = forms.MultipleChoiceField(choices=filter_choices,\
				widget=FilteredSelectMultiple("filter_fields", is_stacked=False))

