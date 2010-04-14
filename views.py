from django.db.models.sql.constants import LOOKUP_SEP
from django.template import RequestContext
from django.shortcuts import render_to_response

from django_customreport.helpers import get_closest_relation, CustomReportDisplaySet, process_queryset
from django_customreport.forms import RelationMultipleChoiceField

class custom_view(object):
	def __new__(cls, request, *args, **kwargs):
		obj = super(custom_view, cls).__new__(cls)
		return obj(request, *args, **kwargs)

	def __call__(cls,request,queryset=None,template_name=None,extra_context=None,form=None):
		cls.template_name = template_name
		cls.request = request
		cls.queryset = queryset
		cls.extra_context = extra_context or {}

		pre_form = cls.get_pre_form(request)
		if request.GET:
			if not 'custom_token' in request.GET:
				pre_form = cls.get_pre_form(request)
				if pre_form.is_valid():
					return cls.render_post_form(filter_fields=pre_form.cleaned_data['filter_fields'])
			else:
				return cls.render_post_form(filter_fields=request.GET.get('filter_fields'))

		return cls.fallback(pre_form=pre_form)

	def get_post_form(self):
		"""
		Meant to be overridden.

		This form is an all-inclusive form with all possible field options attached.
		Fields not selected in the pre-form are deleted from this form and you're
		left with a subset of the original fields.
		"""

		return self.post_form

	def get_pre_form(self,request):
		"""
		Meant to be overridden.

		A pre-form has two required fields: 'display_fields' and 'filter_fields'.

		They are meant to be MultipleChoiceFields and the result is used to modify
		the post form. Any fields not found in the pre-form data are deleted from the
		post form fields.
		"""

		return self.pre_form

	def fallback(self,pre_form=None,post_form=None):
		c = {'pre_form': pre_form, 'post_form': post_form,\
				'custom_token': self.request.GET.get('custom_token',False) }

		c.update(self.extra_context or {})
		return render_to_response(self.template_name, c, context_instance=RequestContext(self.request))

	def render_post_form(self,filter_fields=None):
		filter_fields = filter_fields or []

		form = self.get_post_form()

		filter_fields = self.request.GET.getlist('filter_fields')	

		kept_fields = form.fields.copy()
		for i in form.fields:
			if not i in filter_fields and i != 'display_fields':
				del kept_fields[i]
		form.fields = kept_fields
	
		from django import forms
		form.fields['filter_fields'] = forms.MultipleChoiceField(choices=[(i,i) for i in filter_fields])
		form.initial['filter_fields'] = self.request.GET.get('filter_fields', None) # hacky, breaks with pre. todo.

		if 'custom_token' in self.request.GET and form.is_valid():
			queryset = self.queryset
			from django.db.models.query import QuerySet
			if not isinstance(self.queryset,QuerySet): # it was passed in above
				queryset = self.filter.queryset
			return self.render_results(queryset,display_fields=form.cleaned_data['display_fields'])

		return self.fallback(post_form=form)

	def render_results(self,queryset,display_fields=None):
		return process_queryset(queryset,display_fields=display_fields)

class displayset_view(custom_view):
	"""
	This is a convenience view which will accept five additional arguments.

	1) filter_class - this will build your queryset for you

	http://github.com/alex/django-filter

	If you only want to use one of the above, just subclass and override.

	
	2) displayset_class  - this will easily render your results to an admin-like interface

	http://github.com/subsume/django-displayset

	3) change_list_template - this is the template used above

	"""
	def __call__(cls, filter_class, displayset_class, request, queryset=None,exclusions=None,inclusions=None,depth=None,*args, **kwargs):
		cls.filter_class = filter_class
		cls.filter = filter_class(request.GET or None,queryset=queryset)
		cls.exclusions = exclusions
		cls.depth = depth
		cls.inclusions = inclusions
		cls.displayset_class = displayset_class
		kwargs['extra_context'] = kwargs['extra_context'] or {}
		kwargs['extra_context'].update({'filter': cls.filter})
		return custom_view.__call__(cls,request,queryset=queryset,*args,**kwargs)

	def get_post_form(self):
		form = self.filter.form
		form.fields['display_fields'] = RelationMultipleChoiceField(queryset=\
				self.filter.queryset,depth=self.depth,exclusions=self.exclusions,\
				inclusions=self.inclusions,filter_fields=self.request.GET.getlist('filter_fields'),\
				required=False,label="Additional display fields")
		return form

	def get_pre_form(self,request):
		from django_customreport.forms import FilterSetCustomPreForm
		return FilterSetCustomPreForm(self.filter,request.GET or None,depth=self.depth,exclusions=self.exclusions)

	def render_post_form(self,**kwargs):
		kept_filters = self.filter.filters.copy()
		for i in self.filter.filters:
			if not i in kwargs.get('filter_fields',[]):
				del kept_filters[i]

		self.filter.filters = kept_filters
		return super(displayset_view,self).render_post_form(**kwargs)

	def get_results(self,queryset,display_fields=None):
		filter = self.filter_class(self.request.GET,queryset=queryset)
		return super(displayset_view,self).render_results(filter.qs,display_fields=display_fields)
		
	def render_results(self,queryset,display_fields=None):
		queryset = self.get_results(queryset,display_fields=display_fields)
		self.displayset_class.display_fields = display_fields
		from django_displayset import views as displayset_views
		return displayset_views.generic(self.request,queryset,self.displayset_class,\
				extra_context=self.extra_context)
