# Data model

## Material (generic engineering family / grade)

One record holds the general material selection data: family, repeat unit, default process window, density, heat guide, scores in dry and moisture-conditioned states, real engineering values, source notes, compatibility flags and decision notes.

## Filament product (supplier product)

A material can contain any number of exact supplier products. Each product has brand, product name, supplier URL, colour, spool weight, notes, preferred status and price history.

An owned physical spool should be tracked separately from the generic supplier product. A product is something a shop sells; a spool is the thing you bought, numbered, dried, used and eventually judged.

## Price entry

A filament product can contain many price points. The latest date is used by the calculator and the full history remains visible on the material page.

## Print profile

A saved test profile links to one generic material and optionally one exact spool. It stores real nozzle, bed, chamber, dryer, speed, build plate, result rating and free-form notes.

## Extending properties

Normal editing should happen through field-based forms. `Material.settings_json` and `Material.properties_json` remain available as advanced storage for values that do not yet deserve a first-class field, such as thermal conductivity, dielectric strength, certification, annealing procedure or a measured test value.

Once a property becomes common, expose it in the template and guide scoring instead of making normal users edit JSON like it is a punishment.
