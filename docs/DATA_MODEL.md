# Data model

## Material (generic engineering family / grade)

One record holds the general material selection data: family, repeat unit, default X2D process window, density, heat guide, scores in dry and moisture-conditioned states, and decision notes.

## Filament product (real spool)

A material can contain any number of exact supplier products. Each product has brand, product name, supplier URL, colour, spool weight, notes and preferred status.

## Price entry

A filament product can contain many price points. The latest date is used by the calculator and the full history remains visible on the material page.

## Print profile

A saved test profile links to one generic material and optionally one exact spool. It stores real nozzle, bed, chamber, dryer, speed, build plate, result rating and free-form notes.

## Extending properties

`Material.settings_json` and `Material.properties_json` are intentionally flexible. Add a new property such as thermal conductivity, dielectric strength, certification, annealing procedure or measured test value without a database migration. Once a property becomes common, expose it in the template and guide scoring.
