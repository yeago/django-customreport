import copy

from django import forms
from django.db.models.query import QuerySet

from django.contrib.admin.widgets import FilteredSelectMultiple
from django_customreport.helpers import filter_choice_generator

from django_customreport import models as cm
from django_customreport.helpers import display_list, display_list_redux

class ReportColumnForm(forms.ModelForm):
	def __init__(self,report_site,*args,**kwargs):
		self._report_site = report_site
		super(ReportColumnForm,self).__init__(*args,**kwargs)
		self.fields['human_name'].widget = forms.TextInput()

	def save(self,commit=True):
		instance = super(ReportColumnForm,self).save(commit=False)
		instance.report_site = self._report_site
		instance.save()
		return instance

	class Meta:
		model = cm.ReportColumn
		fields = ['human_name']

class ReportSiteForm(forms.Form):
	def __init__(self,report_site,*args,**kwargs):
		super(ReportSiteForm,self).__init__(*args,**kwargs)
		model = report_site.filterset_class.Meta.model

		non_relation_fields = [(f.name, f.verbose_name)
			for f in model._meta.fields if not hasattr(f.rel, "to")]

		model_methods = []
		for attr in dir(model):
			possible_method = getattr(model,attr)
			try:
				if possible_method.reportable:
					model_methods.append((possible_method.func_name,possible_method.func_name))
			except AttributeError:
				pass

		forward_relations = [("%s-%s-%s" % (f.rel.to._meta.app_label, f.rel.to._meta.object_name, f.name), f.verbose_name)
			for f in model._meta.fields if hasattr(f.rel, "to")]
		backward_relations = [("%s-%s-%s" % (r.model._meta.app_label, r.model._meta.object_name, r.field.related_query_name()),r.field.related_query_name())
			for r in model._meta.get_all_related_objects()]
		choices = non_relation_fields + model_methods + forward_relations + backward_relations

		for key,name in choices:
			self.fields[key] = forms.BooleanField(required=False,label=name)
			if '-' not in key:
				self.fields[key].widget = forms.CheckboxInput(attrs={'class': 'nonrelation'})

class BaseCustomFieldsForm(forms.Form):
	def __init__(self,*args,**kwargs):
		self.queryset = kwargs.pop('queryset')
		super(BaseCustomFieldsForm,self).__init__(*args,**kwargs)

class RelationMultipleChoiceField(forms.MultipleChoiceField):
	def __init__(self,queryset,choices,filter_fields=None,*args,**kwargs):
		filter_fields = filter_fields or []
		choices = filter_choice_generator(choices,queryset,filter_fields)

		kwargs.update({
			'choices': choices,
			'widget': FilteredSelectMultiple("display_fields", is_stacked=False)
		})
		super(RelationMultipleChoiceField,self).__init__(*args,**kwargs)

class ReportForm(forms.ModelForm):
	class Meta:
		model = cm.Report
		fields = ['name','description']

class ColumnForm(forms.Form):
	def __init__(self,report_site,queryset,request,data=None,modules=None,filter_fields=None,**kwargs):
		super(ColumnForm,self).__init__(data or None,**kwargs)
		# these are the values for each filter field
		choices = list(cm.ReportColumn.objects.filter(report_site__site_label=report_site).order_by('-relation'
			).values_list('relation','human_name'))
		self.fields['display_fields'] = RelationMultipleChoiceField(queryset=queryset,\
																	choices=choices,\
																	filter_fields=filter_fields,\
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
