import django_filters
import os

from django.db.models import Max, Sum
from django.test import TestCase

from django_customreport.tests import models as testmodels
from django_customreport.filterset import JoinsafeFilterSet
from django_customreport.helpers import process_queryset

class BasicTest(TestCase):
	fixtures = ['test_data']
	def test_filterset(self):
		"""
		The first person has two locations assigned to them. One is 90210 and its open_saturday,
		one is 32801 and its not open saturday. The below query *should* return 0 results, however,
		a limitation of django_filters queries them separately and therefore we get results when
		we shouldn't.

		"""
		
		#First, we make sure Gaynor's version is still broken

		get_vars = {'location__zip_code': '90210', 'location__open_saturday': '2' }

		class RegularPersonFilterSet(django_filters.FilterSet):
			class Meta:
				model = testmodels.Person
				fields = ('location__zip_code','contact__date','location__open_saturday')

		person_filterset = RegularPersonFilterSet(get_vars,queryset=testmodels.Person.objects.all())

		#self.assertEquals(len(person_filterset.qs),1)

		#Second, we make sure the join-safe version works

		class PersonFilterSet(JoinsafeFilterSet):
			class Meta:
				model = testmodels.Person
				fields = ('location__zip_code','contact__date','location__open_saturday')

		person_filterset = PersonFilterSet(get_vars,queryset=testmodels.Person.objects.all())
		self.assertEquals(len(person_filterset.qs),0)

	def test_results(self):

		"""
		Our fixtures contain 5 people, 3 of whom have each 2 contacts, one inside small_range and one outside.
		One who has only large_range contacts.
		One who has no contacts.

		The sequence hours for the contacts are fibonacci
		"""

		# Dead simple
		qs = process_queryset(testmodels.Person.objects.all())
		self.assertEquals(len(qs),5)

		small_range = ('2010-01-01','2011-01-01')
		large_range = ('2009-01-01','2012-01-01')

		smallrange_qs = testmodels.Person.objects.filter(contact__date__range=small_range)
		largerange_qs = testmodels.Person.objects.filter(contact__date__range=large_range)
		
		# One result per person since its not displaying anything
		qs = process_queryset(smallrange_qs)
		self.assertEquals(len(qs),3)

		# Same
		qs = process_queryset(testmodels.Person.objects.filter(contact__date__range=large_range))
		self.assertEquals(len(qs),4)

		# One result per contact, but its still one per person
		qs = process_queryset(smallrange_qs,display_fields=['contact__date'])
		self.assertEquals(len(qs),3)

		# Same but check aggregated hours
		qs = process_queryset(smallrange_qs,display_fields=['contact__hours'])
		self.assertEquals(qs.aggregate(Sum('contact__hours'))['contact__hours__sum'],12)

		# One result per contact
		qs = process_queryset(largerange_qs,display_fields=['contact__date'])
		self.assertEquals(len(qs),8)

		qs = process_queryset(largerange_qs,display_fields=['contact__hours'])
		self.assertEquals(qs.aggregate(Sum('contact__hours'))['contact__hours__sum'],54)

		# Annotation
		anno_q = testmodels.Person.objects.annotate(Max('contact__date'))
		qs = process_queryset(anno_q)
		self.assertEquals(len(qs),5)

		# Repeating above, just with annotation. Things should return the same results
		qs = process_queryset(smallrange_qs.annotate(Max('contact__date')))
		self.assertEquals(len(qs),3)

		qs = process_queryset(largerange_qs.annotate(Max('contact__date')))
		self.assertEquals(len(qs),4)

		qs = process_queryset(smallrange_qs.annotate(Max('contact__date')),display_fields=['contact__date'])
		self.assertEquals(len(qs),3)

		#These next tests will fail because in django extra() doesn't currently play nice with aggregates

		"""
		qs = process_queryset(smallrange_qs.annotate(Max('contact__date')),display_fields=['contact__hours'])
		self.assertEquals(qs.aggregate(Sum('contact__hours'))['contact__hours__sum'],12)
		
		qs = process_queryset(largerange_qs.annotate(Max('contact__date')),display_fields=['contact__hours'])
		self.assertEquals(qs.aggregate(Sum('contact__hours'))['contact__hours__sum'],54)
		"""

		"""
		This next test will fail because fields are added to the group by column in the event of aggregation
		and the person's two dates are identical.

		No fix up yet.

		qs = process_queryset(largerange_qs.annotate(Max('contact__date')),display_fields=['contact__date'])
		self.assertEquals(len(qs),8)
		"""
		
