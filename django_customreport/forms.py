import copy

from django import forms
from django.db.models.query import QuerySet

from django.contrib.admin.widgets import FilteredSelectMultiple
from django_customreport.helpers import filter_choice_generator

from django_customreport.models import Report, ReportSite
from django_customreport.helpers import display_list, display_list_redux

class ReportSiteForm(forms.ModelForm):
	def __init__(self,report_site,model,*args,**kwargs):
		super(ReportSiteForm,self).__init__(*args,**kwargs)
		instance = kwargs['instance']
		model = report_site.filterset_class.Meta.model
		choices = display_list_redux(model,inclusions=\
			instance.reportcolumn_set.values_list('relation',flat=True))
		self.fields['columns'] = forms.ChoiceField(choices=choices,widget=forms.CheckboxSelectMultiple)

	class Meta:
		model = ReportSite
		exclude = ['site_label']

class BaseCustomFieldsForm(forms.Form):
	def __init__(self,*args,**kwargs):
		self.queryset = kwargs.pop('queryset')
		super(BaseCustomFieldsForm,self).__init__(*args,**kwargs)

class RelationMultipleChoiceField(forms.MultipleChoiceField):
	def __init__(self,queryset,depth=3,inclusions=None,exclusions=None,filter_fields=None,custom_fields=None,*args,**kwargs):
		filter_fields = filter_fields or []
		unfiltered_choices = display_list(queryset,depth=depth,inclusions=inclusions,exclusions=exclusions)
		choices = filter_choice_generator(unfiltered_choices,queryset,filter_fields)
		if custom_fields:
			[choices.insert(0,('custom_%s' % c.name, c.short_description)) for c in custom_fields]

		kwargs.update({
			'choices': choices,
			'widget': FilteredSelectMultiple("display_fields", is_stacked=False)
		})
		super(RelationMultipleChoiceField,self).__init__(*args,**kwargs)

class ReportForm(forms.ModelForm):
	class Meta:
		model = Report
		fields = ['name','description']

class ColumnForm(forms.Form):
	def __init__(self,queryset,request,data=None,inclusions=None,\
			exclusions=None,depth=3,modules=None,filter_fields=None,custom_fields=None,**kwargs):
		super(ColumnForm,self).__init__(data or None,**kwargs)
		# these are the values for each filter field
		self.fields['display_fields'] = RelationMultipleChoiceField(queryset=queryset,\
																	depth=depth,\
																	exclusions=exclusions,\
																	inclusions=inclusions,\
																	filter_fields=filter_fields,\
																	custom_fields=custom_fields,\
																	required=False,\
																	label="Additional display fields")

"""

This form will give you a pre-form based on a filterset where the fields are
chosen before the filterset form is generated.

Its no longer used by default, but still useful in cases where you don't
want to display all fields.

"""

class FilterSetCustomFieldsForm(BaseCustomFieldsForm): # Convenience PreForm which accepts a django-filters filterset
	def __init__(self,filter,data,exclusions=None,inclusions=None,depth=None,queryset=None):
		self._filter = filter
		self._exclusions = exclusions
		self._inclusions = inclusions
		self._depth = depth
		if not isinstance(queryset,QuerySet):
			queryset = filter.queryset

		super(FilterSetCustomFieldsForm,self).__init__(data,queryset=queryset)
		self.update_field_labels() # Separated in case __init__ work wants to change these labels.

	def update_field_labels(self):
		filter_choices = []
		for field, obj in self._filter.base_filters.iteritems():
			value = field
			if '__' in field:
				value = ' :: '.join(field.split('__')[-2:])
			value = ' '.join(value.split('_'))
			filter_choices.append((field,value.title()))

		import operator
		filter_choices = sorted(filter_choices, key=operator.itemgetter(1))

		self.fields['filter_fields'] = forms.MultipleChoiceField(choices=filter_choices,\
				widget=FilteredSelectMultiple("filter_fields", is_stacked=False))
