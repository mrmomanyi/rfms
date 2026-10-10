# RFMS: Forest Resource Monitoring System

A Django system for registering trees, measuring them over time, and turning those
records into carbon (CO2e) and oxygen figures, rankings and maps.

* Project package: `justin`   * App: `momanyi`   * Django 5.x, Python 3.10+

---

## 1. Quick start (new install)

```bash
python -m venv env
env\Scripts\activate            # Windows. On macOS/Linux: source env/bin/activate
pip install -r requirements.txt

python manage.py makemigrations momanyi
python manage.py migrate
python manage.py createsuperuser

python manage.py load_kenya_locations   # 47 counties, 295 sub-counties
python manage.py import_species         # starter species list (edit the CSV first, see section 5)
python manage.py seed_demo_data         # OPTIONAL: sample trees so the dashboards have content

python manage.py runserver
```

Open http://127.0.0.1:8000/ . Commit the `momanyi/migrations/0001_initial.py` file that
`makemigrations` creates.

Check everything with: `python manage.py check` and `python manage.py test`.

Remove demo data later with `python manage.py seed_demo_data --purge`.

## 2. Upgrading your existing project

1. **Back up** your project folder and `db.sqlite3`.
2. Copy these from this package into your project, replacing what is there:
   `momanyi/` (all files except your own `migrations/0001...` files, which you keep),
   `justin/settings.py`, `justin/urls.py`, `requirements.txt`.
3. `pip install -r requirements.txt`
4. `python manage.py makemigrations momanyi` then `python manage.py migrate`.
   All new fields are optional or have defaults, so your existing trees stay.
5. `python manage.py load_kenya_locations` (safe to repeat) and `python manage.py import_species`.

What happens to your existing data:
* Existing trees become **Pending review**. Verify them in the admin site (section 6).
* Trees registered as afforestation or reafforestation use their registration date as the age
  until you add a planting date.
* **Existing forest trees with no measurement are listed as "needs measurement"**
  instead of receiving an invented figure.
* The old per-species carbon and oxygen rates are kept in the database but no longer used.
* `momanyi/templatetags/carbon_filters.py` from the old version is no longer needed.

## 3. What is in the package

| Path | Purpose |
|---|---|
| `momanyi/calculations.py` | The science: growth curve, biomass equation, carbon, oxygen, confidence. No Django imports. |
| `momanyi/services.py` | Evaluates trees and builds totals, rankings and forecasts. No Django imports. |
| `momanyi/selectors.py` | Database queries and the scorecard cache. |
| `momanyi/spatial.py` | Distance maths and the 1 metre duplicate check (database pre-filter first). |
| `momanyi/models.py` | County, SubCounty, TreeSpecies, Tree, Measurement, TreeEvent (audit trail). |
| `momanyi/views.py`, `urls.py`, `forms.py` | Pages, forms, JSON and CSV endpoints. |
| `momanyi/admin.py` | Admin with review actions (verify, reject) and measurement inlines. |
| `momanyi/templates/`, `static/` | Templates, one stylesheet, and the JavaScript for charts, maps and registration. |
| `momanyi/management/commands/` | `load_kenya_locations`, `import_species`, `seed_demo_data`. |
| `momanyi/tests/` | Calculation, scorecard, model, view and admin tests. |

## 4. Pages

| URL | Page | Login |
|---|---|---|
| `/` | Home with live totals | no |
| `/dashboard/` | Registrations, survival rate, review progress | no |
| `/carbon-score/` | CO2e stored, forecast, species, every tree | no |
| `/oxygen-index/` | Oxygen released, by species and tree | no |
| `/rankings/` | Contributors and counties | no |
| `/map/` | Clustered map of all trees | no |
| `/methodology/` | How every number is calculated | no |
| `/tree_registration/` | Register a tree | yes |
| `/trees/<id>/` | One tree: figures, measurements, history | no (editing needs login) |
| `/api/trees/` | GeoJSON for the map (no contributor names) | no |
| `/export/trees.csv` | Every tree with calculated values | staff |
| `/accounts/login/`, `/accounts/signup/` | Accounts | no |
| `/admin/` | Administration | staff |

## 5. Before you publish any figure: replace the placeholders

The calculation engine is sound in structure, but these inputs are **placeholders** until you confirm them:

1. **Wood density per species.** Fill `wood_density` and `density_source` for every species
   (edit `momanyi/data/species_seed.csv` then run `import_species`, or use the admin).
   Source: the Global Wood Density Database. Without it the default 0.60 g/cm3 is used and the
   tree is flagged "default density" on the pages.
2. **Growth curves.** The generic curve (`GrowthParams` in `calculations.py`) is illustrative.
   Give each species its own parameters, calibrated on local measurements.
3. **Root-to-shoot ratio (0.26) and carbon fraction (0.47).** Confirm against the current IPCC
   tables for your forest type.
4. Have a forester (for example KEFRI or Kenya Forest Service) review the method on `/methodology/`.

Measured trees do not depend on the growth curve at all. The more trees have a measurement,
the less the placeholders matter.

## 6. Day-to-day workflow

* **Contributors** sign up, register trees (optionally with a first diameter and height) and later add
  measurements from the tree page.
* **Reviewers** (staff) open *Admin, Trees*, select trees, then choose *Mark selected trees as verified*
  or *rejected*. Each action is written to the tree's history. Rejected trees leave all scores.
* **Rankings** use all living, non-rejected trees by default. To count only verified trees set
  `RFMS_RANK_VERIFIED_ONLY=True`.
* The 1 metre rule, the Kenya bounds and the sub-county check apply in the website **and** in the admin site.

## 7. Settings (environment variables or `.env`)

| Variable | Default | Meaning |
|---|---|---|
| `DJANGO_DEBUG` | `True` | Set `False` in production |
| `DJANGO_SECRET_KEY` | dev key | Required when debug is off |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost` | Comma-separated hosts |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | e.g. `https://rfms.example.org` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | empty | Set `DB_NAME` to use PostgreSQL (`pip install "psycopg[binary]"`) |
| `RFMS_RANK_VERIFIED_ONLY` | `False` | Rank verified trees only |
| `RFMS_SCORECARD_CACHE_SECONDS` | `300` | Scorecard cache lifetime (cleared automatically when trees change) |

Time zone is `Africa/Nairobi`.

## 8. Production checklist

- [ ] `DJANGO_DEBUG=False`, a new `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` set
- [ ] PostgreSQL instead of SQLite, with backups
- [ ] `python manage.py collectstatic`, and serve `staticfiles/` (for example with WhiteNoise or nginx)
- [ ] Run behind HTTPS (set `DJANGO_BEHIND_PROXY=True` if a proxy terminates TLS)
- [ ] `python manage.py check --deploy`
- [ ] Decide your privacy position: rankings show contributor names publicly
- [ ] Replace the placeholders in section 5

## 9. Known limits and suggested next steps

* Contributors are matched by typed name, so "Wanjiku K." and "Wanjiku Kamau" are different people.
  A `Contributor` model with accounts or organisations would fix this.
* Map tiles and place search use OpenStreetMap services. For heavy use, get a tile provider and
  respect the Nominatim usage policy.
* No photo evidence, email verification or rate limiting yet.
* Interface text is English only. Swahili would be added with Django's translation tools.
* The scorecard is computed in Python and cached. At tens of thousands of trees, move it to a
  background job that stores results in the database.
* PostGIS would make spatial queries faster and more precise at large scale.
