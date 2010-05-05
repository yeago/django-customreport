from django.db.models.sql.constants import LOOKUP_SEP
from django.template import RequestContext
from django.shortcuts import render_to_response

from django_customreport.helpers import get_closest_relation, CustomReportDisplaySet, process_queryset
from django_customreport.forms import RelationMultipleChoiceField

class custom_view(object):
	def __new__(cls, request, *args, **kwargs):
		obj = super(custom_view, cls).__new__(cls)
		return obj(request, *args, **kwargs)

	def __call__(cls,request,extra_modules=None,extra_context=None):
		cls.request = request
		cls.extra_context = extra_context or {}
		cls.display_field_inclusions = getattr(cls,'display_field_inclusions',None)
		cls.display_field_exclusions = getattr(cls,'display_field_exclusions',None)
		cls.display_field_depth = getattr(cls,'display_field_depth',None)
		if extra_modules:
			cls.modules = getattr(cls,'modules',None) or {}
			cls.modules.update(extra_modules)

		pre_form = cls.get_pre_form(request)
		if request.GET:
			if not 'custom_token' in request.GET:
				pre_form = cls.get_pre_form(request)
				if pre_form.is_valid():
					return cls.render_post_form(filter_fields=pre_form.cleaned_data['filter_fields'])
			else:
				return cls.render_post_form(filter_fields=request.GET.get('filter_fields'))

		return cls.fallback(pre_form=pre_form)

	def get_pre_form(self,request):
		"""
		Meant to be overridden.

		A pre-form tends to have one field: a list of total options the user has to report.

		We then take their selections and pare-down a second form and only present
		those they select.

		It is meant to be a MultipleChoiceField
		"""
		return self.pre_form

	def get_post_form(self):
		"""
		Meant to be overridden.

		This form is an all-inclusive form with all possible field options attached.
		Fields not selected in the pre-form are deleted from this form and you're
		left with a subset of the original fields.
		"""
		return self.post_form

	def get_query_form(self):
		from django_customreport.forms import QueryForm
		return QueryForm(self.get_queryset(),depth=self.display_field_depth,modules=self.modules,\
				exclusions=self.display_field_exclusions,inclusions=self.display_field_inclusions,\
				filter_fields=self.request.GET.getlist('filter_fields'),\
				initial={'display_fields': self.request.GET.getlist('display_fields')})

	def get_queryset(self):
		"""
		Or override and use self.filter.queryset, for example
		"""

		return self.queryset

	def fallback(self,pre_form=None,post_form=None):
		c = {'pre_form': pre_form, 'post_form': post_form,\
				'custom_token': self.request.GET.get('custom_token',False) }

		c.update(self.extra_context or {})
		return render_to_response(self.template_name, c, context_instance=RequestContext(self.request))

	def render_post_form(self,filter_fields=None,display_fields=None):
		filter_fields = filter_fields or []

		form = self.get_post_form()

		filter_fields = self.request.GET.getlist('filter_fields')

		kept_fields = form.fields.copy()
		for i in form.fields:
			if not i in filter_fields:
				del kept_fields[i]
				
		form.fields = kept_fields
	
		from django import forms
		form.fields['filter_fields'] = forms.MultipleChoiceField(\
				choices=[(i,i) for i in filter_fields],\
				initial=self.request.GET.getlist('filter_fields'))

		if 'custom_token' in self.request.GET and form.is_valid():
			return self.render_results(self.get_queryset(),display_fields=self.request.GET.getlist('display_fields'))

		return self.fallback(post_form=form)

	def get_results(self,queryset,display_fields=None):
		return process_queryset(queryset,display_fields=display_fields)

class displayset_view(custom_view):
	"""
	This is a convenience view which will accept five additional arguments.

	1) filterset_class - this will build your queryset for you

	http://github.com/alex/django-filter

	If you only want to use one of the above, just subclass and override.

	
	2) displayset_class  - this will easily render your results to an admin-like interface

	http://github.com/subsume/django-displayset

	3) change_list_template - this is the template used above

	"""
	def __call__(cls, request, filterset_class=None, displayset_class=None, *args, **kwargs):
		cls.filterset_class = filterset_class or cls.filterset_class
		cls.filter = cls.filterset_class(request.GET or None,queryset=cls.queryset)
		kwargs['extra_context'] = kwargs.get('extra_context') or {}
		kwargs['extra_context'].update({'filter': cls.filter})
		return custom_view.__call__(cls,request,*args,**kwargs)

	def get_pre_form(self,request):
		from django_customreport.forms import FilterSetCustomPreForm
		return FilterSetCustomPreForm(self.filter,request.GET or None)

	def get_post_form(self):
		return self.filter.form

	def get_queryset(self):
		return self.filter.queryset

	def render_post_form(self,**kwargs):
		kept_filters = self.filter.filters.copy()
		for i in self.filter.filters:
			if not i in kwargs.get('filter_fields',[]):
				del kept_filters[i]

		self.filter.filters = kept_filters
		return super(displayset_view,self).render_post_form(**kwargs)

	def get_results(self,queryset,display_fields=None):
		filter = self.filterset_class(self.request.GET,queryset=queryset)
		return super(displayset_view,self).get_results(filter.qs,display_fields=display_fields)
		
	def render_results(self,queryset,display_fields=None):
		queryset = self.get_results(queryset,display_fields=display_fields)
		self.displayset_class.display_fields = display_fields

		if self.request.GET.get('custom_modules',None):
			if self.modules[self.request.GET.get('custom_modules')]:
				return self.modules[self.request.GET.get('custom_modules')](self.request,queryset,extra_context=self.extra_context)

		ff = {}
		for i in self.request.GET.keys():
			if not i in ['submit','filter_fields','custom_token','custom_modules','display_fields']:
				ff[i] = self.request.GET[i]

		self.extra_context.update({'query_form': self.get_query_form(), 'filter_fields': ff})
		
		from django_displayset import views as displayset_views
		return displayset_views.generic(self.request,queryset,self.displayset_class,\
				extra_context=self.extra_context)
