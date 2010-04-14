from django.db import models

class Person(models.Model):
	name = models.CharField(max_length=30)

class Location(models.Model):
	person = models.ForeignKey('Person')
	open_saturday = models.BooleanField()
	zip_code = models.IntegerField()

class Contact(models.Model):
	person = models.ForeignKey('Person')
	hours = models.IntegerField()
	date = models.DateField()
