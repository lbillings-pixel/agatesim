# 72. Reframing: from single forms to coupled processes, in a follow-on project

- Status: accepted (owner, 2026-10-26: the new goal, a new project, and the
  second reading batch)
- Date: 2026-10-25; literature passes 2026-10-26
- Builds on: [ADR 0003](0003-model-architecture.md), [ADR 0004](0004-archetype-ladder.md), [ADR 0005](0005-verification-tiers-and-parameter-natures.md), [ADR 0035](0035-what-the-mechanistic-tier-requires.md), [ADR 0048](0048-shadow-agate-by-a-stated-milkiness-link.md), [ADR 0050](0050-pigments-and-a-palette.md), [ADR 0066](0066-reference-library-and-labelling.md)

## Context

The goal is unchanged: an app that "simulates how natural agate forms inside
its host rock, at the scale of a single nodule or seam". After 71 ADRs, all
thirteen target forms pass at both tiers, and the specimen work (ADRs
0063–0071) has shown how far real specimens are from those single forms. The
owner asked for the project's foundations to be reconsidered, and for an
evaluation of whether a follow-on project would use its lessons better. They
raised four concerns, and supplied an uncited text sketching a "unified
theory" of agate formation for comparison.

The owner also set a standing rule: when a paper or image is blocked, ask
them for it rather than settle for the abstract. They supplied eleven papers
for this ADR, read in full (two by OCR of scans): [@wang1990], [@merino1995],
[@heaney1992], [@heaney1993], [@heaney1995], [@lu1994], [@french2012],
[@moxon2009], [@goetze2018], [@welman2024], [@natkaniec2020].

### The owner's concerns, checked against the code

1. **Either/or where nature is yes/and.** Each form is one preset run by one
   mechanism, or by a fixed chain of stages (ADR 0020). Even the staged model
   runs its processes one after another, each on its own region: dendrites
   grow, then H1 encloses them, and the dendrites never disturb the bands. The
   tagged reference photos show single specimens carrying several forms at
   once, interacting. **Valid.** Sequencing itself is partly right: within
   one fill the order agate bands, coarse quartz, Uruguay bands "is always
   maintained… and never reversed, although it may repeat plural times in one
   geode" ([@lu1994] p.73). What's missing is processes running at the same
   time and feeding back on each other; for example, the particles that
   later settle grow in suspension while the wall lining forms (p.73).
2. **Pigments separate from the impurities that shape growth.** ADR 0050
   states that H1's trace iron and manganese "don't feed back on growth";
   the impurity that drives H1's rhythm is a separate stand-in species. In
   measured agates, "K, Al, Fe, and Na contents oscillate and (mostly)
   oscillate together" band by band ([@merino1995] p.1166). **Valid:** the
   colouring species belong to the same chemistry. Whether iron also changes
   growth has no direct evidence (see Literature).
3. **The list of forms mixes kinds of thing.** The ladder (ADR 0004) puts four
   kinds of phenomenon on one list: banding style (fortification, waterline,
   combined), overall shape (seam, quartz-centre geode, botryoidal), internal
   structures (tube, moss, plume, stick, and eye, which is a spherulite
   structure rather than a shape), and optical effects (shadow, iris; fire
   agate is not yet modelled). Some entries are too broad: "fortification",
   with its angular, zig-zag corners, is one case of wall-parallel banding.
   Some forms are missing, lace agate for one. **Valid.** Each new candidate
   needs a source before it enters any list.
4. **A holistic model may be too costly.** Nanoscale growth can never be
   simulated directly at nodule scale: crystallites are 8–100 nm long
   ([@lu1994] p.56), nodules several centimetres, a span of about 10⁷. A
   multi-scale model carries the small scale as values per grid cell. H1
   already works this way and runs in about 1 s at 512 px (ADR 0050). **Not a
   blocker, on the estimate below; to be measured.**

### Gaps in what the fields carry

`Fields` holds phase (host, chalcedony, void, quartz, inclusion), band index,
one impurity, translucency, deposition time, grain id, micro-band spacing and
an optional pigment name. Two things the science notes (§8) planned are
absent: no opal or moganite phase, so no precursor state, and no fibre
orientation or crystallite size. Translucency is set by stated links
(ADR 0048, the weakest verification) rather than derived from fabric.

## Literature pass (2026-10-26)

What the eleven papers change, with the evidence graded as each paper gives it.

1. **Two candidate banding drivers, not one.**
   - *Impurity-catalysed growth* (H1's family). Wang & Merino's growth law is
     G = α·u·(1+βv)^n with a limit cycle for 1.7 < n < 2.5 ([@wang1990]
     pp.1631, 1634): steep, but not the saturating switch (Hill exponent
     about 4) that our H1 needs (ADR 0013). That choice is ours and must be
     recorded as such. Al was inferred from cathodoluminescence only
     ([@wang1990] p.1630); later probe data show twisted bands hold about
     twice the Al of untwisted ones, at tens of ppm ([@merino1995] p.1162).
   - *Silica polymerisation and depletion.* Partly polymerised fluid
     precipitates defect-rich chalcedony fast until depletion at the fibre
     tips stops polymerisation; slow, nearly perfect quartz grows until
     diffusion restores the silica, with impurities as markers, not drivers
     ([@heaney1995] pp.1563–64). Each band as "a single fluid influx in which
     the solution gradually decreased its extent of silica supersaturation"
     ([@french2012] p.39) fits this picture.
2. **The precursor is disputed.** A gel or polymeric lump ([@wang1990]
   pp.1634–35; [@merino1995] p.1157; "an amorphous silica precursor is
   probably necessary", [@goetze2018] p.12; an opal-C pathway in young
   agates, [@moxon2009] p.566), against a non-viscous, partly polymerised
   solution ([@heaney1993] p.68) or suspended ~10 nm quartz particles
   ([@lu1994] p.73). A model should be able to run either way.
3. **Fabric is sourced in part.**
   - Within each band: an amorphous-plus-nanocrystal zone, then fibrous
     chalcedony, then euhedral quartz, with water falling as crystallinity
     rises ([@french2012] pp.35, 37).
   - Defect-rich, moganite-bearing chalcedony alternates with defect-poor
     quartz at three nested scales, about 0.2 µm, 700 µm and centimetres
     ([@heaney1995] p.1564).
   - Fibre axes follow the local growth direction, re-referenced to each
     band ([@french2012] pp.40–41).
   - Length-slow fibres and high moganite go with alkaline or sulphate-rich
     settings, a field association ([@heaney1992] p.441).
   - Twisting is disputed: Al-dilated fibres ([@merino1995] pp.1158–61)
     against screw dislocations ([@heaney1993] p.70); some extinction bands
     read as twisting are textural ([@lu1994] pp.60–63). Spirals appear only
     in unbanded areas ([@goetze2018] p.13). Twist stays speculative.
4. **Fabric changes after formation.** Crystallite size grows and moganite
   falls over tens to hundreds of millions of years ([@moxon2009] pp.556,
   565–66), and weathered rinds lose moganite ([@heaney1992] p.443). Today's
   fabric is not the formation-time fabric, so a model needs an ageing step.
5. **Iron.** It varies with Al within bands but trends the other way across
   the nodule, and stays when Al vanishes at the quartz centre
   ([@merino1995] pp.1166–67). It is rejected by the growth front
   ([@goetze2018] p.10). Fe³⁺ is among the cations cited as experimental
   catalysts of silica crystallisation ([@wang1990] p.1630), but no paper
   shows iron changing agate growth. So: one shared chemistry, sourced;
   iron feeding back on growth, speculative.
6. **Milkiness.** No source says the fast half of each cycle is milky, as
   ADR 0048 assumes. Scattering belts are micropores and fluid inclusions
   trapped at the growth-rate peak, and bands are visible by the contrast
   between fine twisted and coarse untwisted fibres ([@wang1990] pp.1628,
   1635); water and porosity are highest in the first-formed zone of a band
   ([@french2012] p.37). A fabric-based milkiness rule can replace the
   stated link.
7. **A correction to our docs.** We had said nature records both stage orders
   of fortification and waterline. Within one fill the order is fixed; a
   floor below wall bands comes from a later fill banding over a settled
   floor ([@lu1994] pp.67, 73). The science notes and the combined form's
   summary are corrected; the schedule-set order stands, as a second fill.
   Spherulites in Uruguay bands reach 200 µm, not 100 ([@lu1994] p.73).
8. **Lace.** The one study found uses "blue lace" only as a trade name, calls
   the stone "a typical hydrothermal vein agate", and shows wall-parallel
   bands from both walls of a fissure, contorted around voids that may have
   held rock fragments ([@welman2024] pp.2–4). Lace may be an appearance of
   seam and breccia bodies rather than a banding style of its own. No
   peer-reviewed study of Mexican lace agates was found.
9. **Fire.** The one study found no iron hydroxides, against the usual
   goethite explanation, and assumes, without measuring, that colloform
   "bubble" forms interfere with light ([@natkaniec2020] pp.14, 16). No
   layer thickness is reported. Fire agate can't be modelled from sources
   yet.

### Second batch (2026-10-26)

Five more papers, read in full (one by OCR): [@wang1995], [@frondel1978],
[@frondel1985], [@moxon2013], [@goetze2009].

10. **H1's own source.** Wang & Merino's corrected model has silica and a
    catalyst diffusing through a boundary zone of imposed thickness, the
    catalyst arriving on the silica and left behind at the front. The growth
    law is linear in silica and quadratic in catalyst, "a truncated Taylor's
    expansion", not a saturating switch ([@wang1995] p.57); the mechanism of
    the rate increase is unknown (p.52). What they solve is a two-point
    lumped model, not the full diffusion problem (pp.59–60). Its sustained
    oscillation needs silica to diffuse at most about a fifth as fast as the
    catalyst, so "the initial medium should be dense and polymerized"
    (pp.60–61), and the model holds the far field fixed, so the oscillation
    never ends there. Three consequences for us:
    - our Hill exponent of about 4 is our own choice (as item 1 says);
    - our explicit-diffusion H1 rarely oscillating (ADRs 0017, 0028) does
      not contradict theirs, which was never solved with explicit
      diffusion;
    - the diffusivity ratio is a condition the trial must check in H1.
    The same paper derives fibre width from an instability of the front,
    about 5 µm, finer and twisted when the catalyst is high (pp.64–71).
11. **Water micro-zoning.** Structural water zones in micrometre units, often
    palindromic, disordered early in the fill and ordered late, and ordered
    only in closed cavities ([@frondel1985] pp.975–78); they make iris agate
    where translucent (p.976). Frondel reads the visible bands as "chance
    variations in the deposition of pigmenting impurities" (p.977), against
    the band-by-band chemistry of [@merino1995]: one more open question, not
    a settled one. Fibres nearer perpendicular to the wall win the
    competition after minute divergent spherulites; twist periods are 20–700
    µm ([@frondel1978]).
12. **Horizontal banding.** In a survey of 73 agates, the commonest layouts
    are a horizontal lower section under wall bands (41%) and wall bands
    around a horizontal centre (33%) ([@moxon2013] p.233). Horizontal bands
    have larger crystallites, less moganite and water, up to 20 times more
    Al, and less fibrosity than wall bands; each is a discrete batch, with Al
    varying between bands and not within (pp.235–41). Wall bands grown on a
    flat floor stand as vertical reeds (pp.239–40). Settling of colloidal
    silica "can only be part of the story" (p.245). The 7–27 Myr gap between
    the two band types rests on assuming both fabrics coarsen alike.
13. **Iron, again.** In red sedimentary agates, iron sits in hematite
    particles, some aligned along growth fronts, about 70 times richer in
    chalcedony than in quartz, yet "no correlation of trace elements with the
    agate banding is detectable" ([@goetze2009] pp.680–88). Iron and titanium
    were below detection in Brazilian bands ([@moxon2013] p.235). No paper in
    either batch shows iron changing silica growth: iron stays a passive
    tracer, with feedback off by default and graded speculative.

## The "unified theory" text compared

The text has no citations, so under the catalogue rule it is a framing, not a
source. Against the sources:

**Agrees with our sources and results**
- Agate starts from non-crystalline silica ([@goetze2020] §6,
  [@moxon2020] §5), though whether that is a gel, a sol or a suspension is
  disputed (Literature, item 2).
- Growth starts at the wall ([@goetze2020] §4.1.2, §5.4).
- Banding is self-organised at the growth front ([@goetze2020] §5.4).
- Clear quartz grows at the centre once the polymerised silica is used up
  ([@goetze2020] §6, [@heaney1993] p.72); reproduced without a schedule
  (ADR 0037).
- Its chalcedony–quartz alternation is observed: defect-rich chalcedony and
  defect-poor quartz alternate at three nested scales ([@heaney1995] p.1564),
  and Heaney and Davis explain it by a polymerisation switch, close to the
  text's "relief valve".
- Episodic fluid pulses fit the condition schedules (ADR 0003, 0007), and
  repeated fills are observed ([@lu1994] p.73).

**Diverges from our sources or results**
- It credits Liesegang-type banding with sharp fortification bands. In our
  models, Liesegang rings round corners over 1.6–2.4 band spacings, against
  0.03–0.63 measured on photos (ADRs 0015, 0026); both reviews disfavour
  Liesegang banding in a gel ([@goetze2020] §5.4, [@moxon2020] §5), and
  Liesegang banding is "extremely rare in agates" ([@heaney1993] p.68).
  Heaney and Davis do call their front cycles "Ostwald-Liesegang", but those
  are cycles at the growth front, not rings in a gel ([@heaney1995] p.1563).
- It says Brazil twinning forces the fibres to twist. Heaney ties twinning to
  growth errors and twisting to dislocation strain ([@heaney1993] pp.70–72);
  Merino and coworkers tie twisting to Al ([@merino1995]). Neither has it as
  the text does.

**Rightly points at what we lack**
- A precursor state: degree of silica polymerisation, opal, gel, sol or
  suspended particles.
- Nanoscale fabric: defect density, moganite, crystallite size, water, fibre
  orientation, as the basis of milkiness and so of shadow agate.
- One chemistry shared across scales.

## Decision

1. **agatesim is complete as a first project:** "which single mechanisms
   and conditions can produce which forms". Its verified results, tests and
   ADRs stand and are not rebuilt. It continues to receive fixes and the
   specimen work in progress, and becomes a library for the follow-on.
2. **A follow-on project**, separate from agatesim (name and repository to
   be chosen), with a new goal:
   *explore how formation processes interact within a single nodule or seam,
   and which combinations of conditions give the mixtures of forms seen in
   real specimens.*
3. **Graded claims replace pass/fail as the main output.**
   - *Verified:* as now (ADR 0035), where a result earns it.
   - *Plausible:* every process has a source, but the couplings between them
     are assumed and stated.
   - *Speculative:* a process or coupling without a source.
   Procedural results stay what they are: never evidence for a mechanism.
4. **A faceted taxonomy**, set in its own ADR before any code: banding style,
   body shape, internal structures, optical effects. A specimen or a result
   carries a value on each facet, so one nodule can be "wall-parallel
   banding, angular (fortification), with moss and a quartz centre". New
   candidates (lace, fire, and others) enter only with a source and owner
   approval.
5. **One shared, evolving state; processes run together on it.**
   - *Chemistry,* at the front and in the cavity reservoir: silica as monomer
     and as polymer or particles; Al with Na and K as one coupled
     substitution; Fe with its redox state; Mn; water; pH. Pigments are these
     same species, and colour is derived from them by the renderer. Iron is
     rejected at the front and carried as aligned oxide particles; its
     feedback on growth is an option, off by default (items 5, 13).
   - *Two banding drivers,* selectable and combinable: impurity-catalysed
     growth ([@wang1990]) and polymerisation depletion ([@heaney1995]).
     Neither is preferred until a test tells them apart.
   - *A reservoir that runs as gel or as solution,* closed or resupplied by
     fills.
   - *Fabric per cell,* at deposition: phase fractions (amorphous or opal,
     fibrous chalcedony, quartz), moganite share, crystallite size, water,
     porosity and inclusions, defect density, fibre axis (the local growth
     direction), length-fast or length-slow. Twist only as a speculative
     option.
   - *Ageing after formation:* crystallite growth and moganite loss with age
     ([@moxon2009]), rind alteration ([@heaney1992]).
   - *Optics from fabric:* milkiness from porosity, inclusions and
     crystallite contrast, replacing the stated link of ADR 0048; iris from
     the finest scale.
   - *Horizontal bands as batches:* each settled layer carries its own
     chemistry and fabric (coarser, less fibrous, Al-rich), with an optional
     gravity direction per batch for a host that tilted between fills
     (item 12).
   - *Processes* taken from agatesim as components: front growth (H1),
     settling (H4) of particles grown in suspension during lining, dendrite
     aggregation, chemical gardens, crystal growth, nucleation, all acting in
     the same time step where they coexist.
6. **The reference library is the yardstick.** Simulated nodules are judged
   by whether they show the mixtures and interplay of forms seen in the
   library, scored by the classifier and feature maps (ADRs 0067–0071), as
   well as by the existing criteria. Specimen photos stay on the PC, as now.
   Horizontal bands alone don't prove settling: later agate bands on a
   settled floor can look horizontal ([@lu1994] pp.67–69).
7. **Reused from agatesim, not copied:** geometry, rendering and optics, 3D
   cuts and surveys, criteria, specimen analysis, classifier and maps, GPU
   and compiled solvers, progress and estimates, the web app shell, the
   reference catalogue and the ADR practice.

## Alternatives considered

- **Rework agatesim in place.** Keeps one repository, but the archetype
  ladder, the per-form presets and CI checks, and `Fields` are its backbone;
  changing them breaks 71 ADRs' worth of verified claims and their tests.
  Not chosen.
- **A new package inside this repository.** A middle course: shared CI and
  web app, separate goal. Not chosen: the owner preferred a new project.
- **No change.** Leaves the four valid concerns standing.

## Risks

- **Convincing but unfounded.** Most couplings have no measured value; the
  reading confirms that the banding driver, the precursor and twisting are
  all disputed. Guarded by graded claims, selectable alternatives, a source
  for every process, stated couplings, and the library as an outside check.
- **Cost.** Untested estimate: a coupled 2D nodule in seconds to a minute on
  the RTX 4070, a coarse 3D one in minutes. To be measured in the trial and
  recorded in `agatesim.estimate`.
- **Scope.** A follow-on project could grow without limit. It starts with a
  2D trial of three couplings only.

## Next steps

1. **Name and set up the new project** (owner chooses the name; a new
   repository is outward-facing, so it waits for the owner's go-ahead).
2. **Taxonomy ADR** (decision 4), approved by the owner, in the new project.
3. **Architecture ADR and a 2D trial:** a shared chemistry with both banding
   drivers, fabric per cell with a milkiness rule, and settling of particles
   grown during lining. Check H1's diffusivity ratio against item 10. Measure
   time and memory.
4. **Further reading, when a step needs it:** Moxon 1996 on Fe³⁺ and silica
   co-precipitation (the direct test of iron feedback), Petránek 2004 on
   gravitational (Uruguay-type) banding, Wang & Merino 1992 (the lumped
   model's analysis), Frondel 1982 on structural water, and any source on
   Mexican lace agates.

## Consequences

- agatesim's scope is now fixed as its first project: fixes and the specimen
  work in progress continue, new formation modelling goes to the follow-on.
- Science notes corrected on stage order and Uruguay spherulite size; the
  combined form's summary corrected (registry and `docs/archetypes.md`).
- Catalogue: six sources raised to full text, ten added.
- H1's switch-like catalysis and ADR 0048's milkiness link are now recorded
  as our own assumptions, not as the sources'.
