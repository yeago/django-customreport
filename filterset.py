from django_filters import FilterSet

class JoinsafeFilterSet(FilterSet):
	"""

	This is here until Alex Gaynor gets around to fixing:

	http://github.com/alex/django-filter/issues#issue/24

	Essentially we stitch together all querying done in the filterset so that
	filtering produces no more than 1 join per table. This translates to distant
	relations being filtered together and correcting the paradox of filtering
	on:
	
	people = People.filter(address__city_name='Miami')

	and:

	people.filter(address__city_zip='90210')

	And ending up with Californians and Floridians.

	In reality, we should have 0 results.
	"""

	@property
	def qs(self):

		"""
		We call this here because select_related doesn't add anything to
		table map until sql is generated. It would make all select_related
		look like new additions to the query.
		"""
		self.queryset.query.get_compiler('default').as_sql()
		import copy
		original_table_map = copy.deepcopy(self.queryset.query.table_map)


		qs = super(JoinsafeFilterSet,self).qs
		
		redux_table_map = {}
		removed_tables = {} 

		"""
		We cycle through the table map as it came out of the FilterSet
		"""

		for table_name, tables in qs.query.table_map.iteritems():
			if table_name in original_table_map:
				redux_table_map[table_name] = tables # default, override next if necc.
				"""
				if it exists in the original table map, we check to see if
				it created an additional join. If it did, we only allow it to create
				one more join. We always use the last join.
				"""
				if len(tables) > len(original_table_map[table_name]):
					redux_table_map[table_name] = original_table_map[table_name]
					#redux_table_map[table_name].append(tables[-1])

			else:
				"""
				If it didn't exist, we keep only one of the joins it created

				We use the first (tables[0]) because we hopefully don't have to update
				the alias map, too.
				"""

				redux_table_map[table_name] = [tables[0]]

			for i in tables:
				if not i in redux_table_map[table_name]:
					if not i in removed_tables:
						removed_tables[i] = []
						qs.query.unref_alias(i)

					new_alias = redux_table_map[table_name][-1]
					removed_tables[i].append(new_alias)
					qs.query.where.relabel_aliases({i: new_alias})

		redux_join_map = {}

		for join_tuple, tables in qs.query.join_map.iteritems():
			redux_join_map[join_tuple] = [t for t in tables if not t in removed_tables]
		
		redux_alias_map = {}

		for k, v in qs.query.alias_map.iteritems():
			if not k in removed_tables:
				redux_alias_map[k] = v

			if v[3] in removed_tables:
				"""
				Damn you ORM.
				"""
				redux_alias_map[k] = (v[0],v[1],v[2],removed_tables[v[3]][0],v[4],v[5],v[6])

		qs.query.table_map = redux_table_map
		qs.query.join_map = redux_join_map
		qs.query.alias_map = redux_alias_map
		return qs
