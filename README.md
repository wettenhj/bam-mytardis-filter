BAM MyTardis Filter
===================

Filter for storing BAM file metadata for MyTardis using samtools.

## Requirements
 - samtools

## Installation

 - Install samtools

Git clone this repository into `/path/to/mytardis/tardis/tardis_portal/filters`:
    
    git clone git@github.com:wettenhj/bam-mytardis-filter.git bam

Add the following to your MyTardis settings file eg. `/path/to/mytardis/tardis/settings.py`

```
MIDDLEWARE_CLASSES = MIDDLEWARE_CLASSES + ('tardis.tardis_portal.filters.FilterInitMiddleware',)

FILTER_MIDDLEWARE = (("tardis.tardis_portal.filters", "FilterInitMiddleware"),)
```

The above enables the filter middleware for all actions.

Then add the definition for this filter.

```
POST_SAVE_FILTERS = [
   ("tardis.tardis_portal.filters.bamfilter.bamfilter.make_filter",
   ["BAM", "http://tardis.edu.au/schemas/bam/1",
    "/path/to/samtools/samtool"]),
   ]
```

Where the samtools directory is correct for your installation.

`cd /path/to/mytardis` and load the parameter schema into the MyTardis database:

```
bin/django loaddata tardis/tardis_portal/filters/bam/bam.json
```

Restart MyTardis. From now on, all bam files loaded will have metadata extracted and stored alongside the file itself.
