from django_filters import FilterSet

class JoinsafeFilterSet(FilterSet):
	"""

	This is here until Alex Gaynor gets around to fixing:

	http://github.com/alex/django-filter/issues#issue/24

	Essentially we stitch together all querying done in the filterset so that
	filtering produces no more than 1 join per table. This translates to distant
	relations being filtered together and correcting the paradox of filtering
	on 
	People(address_city='Miami')

	and

	People(address_city__zip='90210')

	And ending up with Californians and Floridians.

	In reality, we should have 0 results.
	"""

	@property
	def qs(self):
		import copy
		original_table_map = copy.deepcopy(self.queryset.query.table_map)

		qs = super(JoinsafeFilterSet,self).qs

		new_table_map = copy.deepcopy(qs.query.table_map)
		redux_table_map = {}
		removed_tables = {} 

		for table_name, tables in new_table_map.iteritems():
			if table_name in original_table_map:
				if len(tables) > len(original_table_map[table_name]):
					redux_table_map[table_name] = original_table_map[table_name]
					redux_table_map[table_name].append(tables[-1])

				else:
					redux_table_map[table_name] = tables

			else:
				redux_table_map[table_name] = [tables[0]]

			for i in tables:
				if not i in redux_table_map[table_name]:
					removed_tables[i] = table_name #new_table_map[table_name][-1]

		redux_join_map = {}

		for join_tuple, tables in qs.query.join_map.iteritems():
			redux_join_map[join_tuple] = [t for t in tables if not t in removed_tables]

		redux_alias_map = {}

		for k, v in qs.query.alias_map.iteritems():
			if not k in removed_tables:
				redux_alias_map[k] = v

		qs.query.table_map = redux_table_map
		qs.query.join_map = redux_join_map
		qs.query.alias_map = redux_alias_map
		for key, value in removed_tables.iteritems():
			qs.query.unref_alias(key)

		qs.query.where.relabel_aliases(removed_tables)
		return qs
