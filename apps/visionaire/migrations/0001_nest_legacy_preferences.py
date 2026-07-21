'''	FR-12 data migration.

	Nests any pre-existing, non-versioned (flat) content of `UserPref.viewer` AND
	`UserPref.studylist` under a "0.3" key, so the frontend version-resolution/backfill
	(FR-10) can migrate users forward on first load. Null/empty fields and
	already-versioned documents are left untouched. Forward-only; the reverse operation is
	a no-op. The transform is idempotent -- safe to re-run against already-migrated data.

	NOTE (delivery mechanism): this project remaps the `visionaire` app's migrations to an
	external, deploy-generated module via the site config `[Database-Migrations]` entry
	(`visionaire = dbmigrations.visionaire`), so committed app migrations are not
	auto-discovered under the standard configuration and no schema migrations live in the
	repo. The transform itself lives in -- and is unit-tested via --
	`UserPref.nest_legacy_document`, independent of the migration graph. When wiring this
	migration into the active migration module, set `dependencies` to the latest
	`visionaire` schema migration so it runs after the table exists.
'''
from django.db import migrations


def nest_legacy_preferences(apps, schema_editor):
	'''	Apply UserPref.nest_legacy_document to every row's `viewer` and `studylist`
		fields. Uses the historical model to iterate rows and the (pure, stateless)
		model transform for the logic.
	'''
	from visionaire.models.userpref import UserPref as UserPrefModel, PREF_FIELDS

	UserPref = apps.get_model('visionaire', 'UserPref')
	for userpref in UserPref.objects.all():
		updated_fields = []
		for field in PREF_FIELDS:
			current = getattr(userpref, field)
			nested = UserPrefModel.nest_legacy_document(current)
			if nested != current:
				setattr(userpref, field, nested)
				updated_fields.append(field)
		if updated_fields:
			userpref.save(update_fields=updated_fields)


class Migration(migrations.Migration):

	# See the module docstring: set this to the latest `visionaire` schema migration when
	# the file is placed in the active (deploy-generated) migration module.
	dependencies = []

	operations = [
		migrations.RunPython(nest_legacy_preferences, migrations.RunPython.noop),
	]
