# 66. A reference library of open-licence photos, and a labelling screen

- Status: accepted (M31, stage 2 of [ADR 0063](0063-specimen-work-restarted-in-stages.md))
- Date: 2026-10-24

## Context

The classifier planned for M32 needs labelled photos of each form. ADR 0063
plans a committed sources list in three tiers, images fetched on demand, a quick
labelling screen, regression tests on the reference photos (promised by ADR 0006
point 5 and never written), and the quality gate in place of the hand-set
`analysis_ready` flag. The owner chose a first library of about 300 photos (about
150 MB) and a labelling screen that works on a phone over the remote link.

## Decision

### 1. Sources list (`references/library.toml`)

- `scripts/build_library.py` walks 18 agate categories on Wikimedia Commons, to
  a depth of three (banded, moss, tube, nodules, textures, by country and so
  on). Categories of worked stone are skipped: objects, art, jewellery, dyed
  stone, sardonyx cameos.
- A photo qualifies if it meets all of these:
  - a JPEG or PNG at least 800 px on its short side (a 1280 px copy is fetched, a standard Commons size; smaller originals as they are);
  - public domain, CC0, CC BY or CC BY-SA, so tier 1;
  - a named author;
  - no jewellery or object words in its title.
- 750 photos qualified out of 928. 300 were kept, rarest guessed form first, so
  that no form takes more than an eighth of the list while others are short.
- Each entry records:
  - title and Commons page;
  - author and licence;
  - the URL of a 1280 px copy;
  - the date retrieved;
  - its categories;
  - guessed forms.
- Re-running the script keeps existing entries as they are, so ids and labels
  stay put.
- Guesses come from words in the title and categories. They only pre-fill the
  labelling screen and are never labels.
- `agatesim library fetch` downloads the listed photos into `references/library/`
  (gitignored). It is resumable; `agatesim library status` counts photos listed,
  fetched and labelled. Tiers 2 and 3 still need the owner's approval per source.

### 2. Labels (`references/library-labels.toml`, committed)

A photo's label is one of three verdicts:

- **forms**: one or more archetype ids from the registry;
- **can't tell**;
- **not usable**: not a specimen as it formed, or too poor to judge.

A label may also be marked "not sure", list features (quartz core, open cavity,
inclusions, host rock, polished, rough, iridescence) and carry a note.
Iridescence was added after the first 75 labels, for fire agate: its play of
colour is clear in photos but is not a form any model makes (roadmap M36). The file is sorted by
id, so its history reads cleanly. Labels say what a photo looks like and are
never evidence for a formation mechanism. The owner's own photos are labelled
apart from the library and never enter this file.

### 3. Labelling screen (Specimens → Reference labels)

- One photo at a time, with its title, author and licence linked.
- Chips sized for a thumb: forms, features and "not sure".
- Guessed forms show dashed until confirmed.
- Buttons: Save, Can't tell, Not usable, Skip, Back. Saving moves to the next
  photo still unlabelled.
- Only library photos are served on this screen (`/api/library`), never the
  owner's specimens. So it is safe over the remote link, where anyone who has the
  link could also change labels: the committed file's diff is what gets reviewed.

### 4. Reference photos as regression data

`tests/data/reference_regression.json` records what photo analysis now makes of
the 12 cut-slab photos in `references/images/`. For each photo it records:

- the quality gate's classification badge;
- the forms the criteria pass, assuming a face 60 mm across, since the photos
  carry no scale.

The test fails on any change, better or worse, which is then looked at and
re-recorded on purpose (`scripts/reference_regression.py --write`).

The first record is plain: **0 of 24 catalogued forms are recognised**, and only
6 of the 12 photos are fit for classification. This is the audit's finding (ADR
0063) in numbers, and the baseline M32's classifier is measured against.

### 5. `analysis_ready` removed

`analysis_ready` is removed from the image catalogue. The quality gate measures
the same thing and is recorded in the snapshot.

## Consequences

- Building the list takes about 10 minutes (Commons rate limits: 1.5 s between
  requests). Fetching takes a few minutes for about 150 MB.
- The reference regression test adds about 50 s to the suite.
- Labelling 300 photos by tapping is the main cost of this stage. The guesses
  help with common forms, but rare ones (shadow, stick, iris) have few photos,
  and M32 will need simulated slabs to fill the gap.
- Procedural and label data say nothing about formation mechanisms.
