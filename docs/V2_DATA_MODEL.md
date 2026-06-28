# Material Lab V2 — Data Model

**Status:** Draft
**Purpose:** Define how Material Lab stores engineering data, real products, physical spools, personal testing, prices, and calculated material scores.

---

## 1. Core principles

1. Every material, product, spool, property, source, note, and test result must be editable.
2. No important engineering score may exist without underlying raw data or an explicitly documented manual estimate.
3. Published/reference data and personal measured data must remain separate.
4. A physical spool must never overwrite the generic properties of its material.
5. Personal data belongs to the local database and must not be committed to GitHub.
6. Material Lab must preserve source, test condition, state, date, and confidence wherever technically relevant.
7. Deleting records that are already used by other records should normally archive them instead.

---

## 2. Entity hierarchy

```text
Material Family
└── Material Variant
    └── Filament Product
        └── Physical Spool
            └── Print Profile
                └── Print Result / Personal Test
```

Example:

```text
Material Family
└── Polyamide
    └── PA6-CF
        └── Bambu Lab PA6-CF
            └── Black 1 kg spool bought by Tom
                └── X2D 0.6 mm tungsten-carbide profile
                    └── Successful structural bracket print
```

---

## 3. Material Family

A material family is a broad polymer group.

Examples:

* PLA
* PETG
* ABS
* ASA
* TPU
* Polyamide
* Polycarbonate
* Polyphthalamide
* Polyether ether ketone

A family stores:

* Name
* Description
* Default family colour
* General chemistry notes
* General safety notes
* General material behaviour

A family does not represent one exact printable filament.

---

## 4. Material Variant

A material variant is the engineering material that is compared, rated, and selected.

Examples:

* PETG
* PETG-CF
* ASA
* ASA-CF
* PA6
* PA6-CF
* PAHT-CF
* PET-CF
* PPA-CF

A material variant stores:

* Short name
* Full chemical name
* Material family
* Reinforcement type: none, carbon fibre, glass fibre, mineral, flame-retardant, other
* Polymer repeat unit / simplified structural representation
* Family colour and variant accent colour
* Base engineering properties
* Default X2D process recommendations
* Material-selection guidance
* Published sources and confidence information

A material variant is editable and may be archived.

---

## 5. Filament Product

A filament product is a real product sold by a manufacturer.

Examples:

* Bambu Lab PA6-CF
* Polymaker Fiberon PA6-CF
* Prusament PETG
* Extrudr DuraPro ASA
* eSUN PETG

A product stores:

* Manufacturer
* Exact product name
* Material variant
* Product URL
* Technical data sheet URL
* Filament diameter
* Available colours
* Manufacturer-specific print settings
* Manufacturer-specific mechanical data
* Certification or safety information
* Notes
* Active / archived status

A product may have multiple historical prices and multiple physical spools.

---

## 6. Physical Spool

A physical spool is one item owned, tested, planned, or previously owned by the user.

A spool stores:

* Product
* Colour name
* Colour hex value or visual swatch
* Spool mass when new
* Remaining mass
* Purchase price
* Calculated purchase price per kilogram
* Supplier
* Supplier URL
* Purchase date
* Batch / lot number
* Storage location
* Drying status
* Last dried date
* Current condition
* Personal notes
* Status: planned, owned, empty, archived

A physical spool is the source used by the calculator when calculating real print cost.

---

## 7. Property Data

Every engineering property must be stored as raw data before it becomes a visual score.

Examples of raw properties:

* Density in g/cm³
* Tensile strength in MPa
* Tensile modulus in GPa
* Flexural strength in MPa
* Flexural modulus in GPa
* Izod or Charpy impact strength
* HDT in °C
* Glass-transition temperature in °C
* Melting temperature in °C
* Water absorption in %
* Shrinkage in %
* Thermal conductivity
* Electrical resistivity
* Continuous-use temperature
* Flammability classification
* UV resistance
* Chemical resistance notes
* Creep resistance
* Layer adhesion measurements

Every raw property record should support:

* Numeric value or controlled qualitative value
* Unit
* Test standard, where known
* Test condition
* Material state: dry, conditioned, wet, unknown
* Source type: manufacturer, paper, literature, user measurement, estimated
* Source URL or document reference
* Confidence: high, medium, low
* Date added
* Notes

---

## 8. Calculated Visual Scores

Material Lab may show visual scores from 0 to 10, but they must be calculated from raw data.

Initial calculated scores:

* XY stiffness
* XY tensile strength
* Z / layer-direction strength
* Layer adhesion
* Impact resistance
* Heat resistance
* Moisture sensitivity
* Water resistance
* Chemical resistance
* UV resistance
* Ease of printing
* Dimensional stability
* Creep resistance

Rules:

1. The user can inspect the raw values and formula inputs behind every score.
2. Scores must show whether they represent dry, conditioned, wet, or unknown material state.
3. Scores should use published data by default.
4. Personal measurements may be displayed separately and may later be used as an optional personal-score mode.
5. Manual score overrides are allowed only with a written reason.
6. Price is not a 0–10 score.

---

## 9. Prices

Prices are always stored as real currency values.

Material Lab should calculate:

* Latest observed price per kilogram
* Lowest observed price per kilogram
* Highest observed price per kilogram
* Median observed price per kilogram
* User-owned spool cost per kilogram
* Historical price trend

A price record stores:

* Product or spool
* Supplier
* Currency
* Total price
* Net filament mass
* Calculated price per kilogram
* Date observed or purchased
* Source URL
* Shipping included: yes / no / unknown
* Notes

---

## 10. Personal Tests and Print Results

Personal testing must remain separate from published manufacturer data.

A personal test or print result stores:

* Physical spool
* Printer
* Nozzle type and diameter
* Nozzle temperature
* Bed temperature
* Chamber temperature
* Cooling setting
* Print speed
* Layer height
* Build plate
* Drying process
* Print orientation
* Part or test specimen type
* Measured result, if available
* Visual result rating
* Failure mode
* Photos or files in the future
* Notes
* Date

Example:

```text
Published value:
PA6-CF tensile strength = 102 MPa
State = dry
Source = manufacturer technical data sheet

Personal result:
Bambu PA6-CF black spool
X2D, 0.6 mm tungsten carbide
290 °C nozzle, 100 °C bed, 60 °C chamber
Dried at 80 °C for 12 hours
Vertical print orientation
Observed result = good surface, layer split under extreme bending
```

---

## 11. Data safety

The application code belongs in GitHub.

Personal live data belongs only in the local persistent data directory:

```text
data/
```

This includes:

* SQLite database
* Price history
* Personal spool information
* Personal notes
* Print profiles
* Test results
* Future photos and uploaded data sheets

The `data/` directory must be backed up separately and must not be committed to GitHub.
