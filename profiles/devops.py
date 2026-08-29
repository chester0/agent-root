"""Tripwire manifest for a PHP/Laravel + Vue + Python + Helm/Docker (+ Terraform) shop.

Drop this in as `DOMAINS` in `scripts/tripwires.py`, or import it.

⭐ READ THIS BEFORE USING IT

The `rules` below are **questions and checks, not facts**. That is deliberate and
it is the single most important design decision in this whole kernel.

A starter pack that asserts things about YOUR system - "the staging cluster
autoscales", "migrations are always reversible" - is wrong on day one and
trusted anyway. Worse, it displaces the real knowledge someone would otherwise
have written, because the file already looks maintained.

So every line here is either:
  - a check to run BEFORE a class of change, or
  - a question whose answer belongs in `DECISIONS.md` once someone knows it.

⚠️ **Replace them with real rules as incidents earn them.** A rule that cites the
outage it came from is worth twenty that sound sensible. The starter pack is
scaffolding for the first month, not the destination - and if a line here is
still unedited in six months, delete it rather than leave a question posing as
knowledge.
"""

DOMAINS = [
    {
        "name": "terraform-state",
        "traps_scope": "terraform",
        "when": (
            "writing or applying Terraform, importing existing infrastructure, "
            "touching state, or migrating click-ops resources into code"
        ),
        "apply_to": "**/*.tf,**/*.tfvars,**/.terraform.lock.hcl,**/terraform/**,**/infra/**",
        "rules": [
            "**Read the plan, every line, before apply.** In a click-ops migration "
            "the dangerous output is not `+ create`, it is `- destroy` on something "
            "a human made by hand and nobody imported.",
            "**Which resources are NOT yet imported?** Anything real but absent "
            "from state will be recreated or destroyed by a confident apply. "
            "`terraform state list` against reality is the migration's actual map — "
            "record the gap in `DECISIONS.md`.",
            "**Blast radius before elegance.** Which resources force replacement on "
            "change (identifiers, subnets, engine versions)? Which are referenced "
            "from ANOTHER state via remote state or data sources? A tidy refactor "
            "that recreates a database is not a refactor.",
            "**Who else can change this?** If the console is still open to people, "
            "state drifts between plan and apply. Say so in `DECISIONS.md` rather "
            "than being surprised twice.",
            "**Where does state live, what locks it, and who else can write it?** A "
            "second engineer running apply against the same unlocked backend is how "
            "state gets corrupted. Note the backend, the lock table and who has "
            "credentials. And treat `-target` and workspace switches as incidents "
            "worth recording, not routine.",
            "⭐ **Record why, not just what.** `terraform import`, state surgery, "
            "and every ugly rule kept because prod depends on it — a click-ops "
            "migration IS the act of turning tribal memory into text. That text "
            "lands in `DECISIONS.md` or it is lost again.",
        ],
    },
    {
        "name": "helm-k8s",
        "traps_scope": "charts",
        "when": (
            "editing Helm charts or values, Kubernetes manifests, rollouts, "
            "resource limits, probes, or anything that changes what runs in a cluster"
        ),
        "apply_to": "**/Chart.yaml,**/values*.yaml,**/charts/**,**/k8s/**,**/manifests/**,**/templates/*.yaml",
        "rules": [
            "**`helm diff upgrade` before `helm upgrade`** (`helm-diff` is a PLUGIN, not "
            "built in - install it or this advice fails on first use). Rendered "
            "output is the truth; the values file is only the intent.",
            "**Which values file actually applies here?** Environment overlays and "
            "`--set` flags in CI silently outrank the defaults you are reading.",
            "**Probes and limits are outage material.** A liveness probe that is "
            "stricter than real startup time restarts a healthy pod forever; a "
            "memory limit below real peak gets it OOMKilled under exactly the load "
            "you needed it for.",
            "**Is this change safe to roll back?** A schema change shipped with the "
            "deploy usually is not — which makes it a `DECISIONS.md` entry, not "
            "just a commit.",
            "**Secrets do not belong in values.** Check what the chart expects and "
            "where it really comes from before adding a key.",
        ],
    },
    {
        "name": "laravel-migrations",
        "traps_scope": "database",
        "when": (
            "writing Laravel migrations, changing the schema, touching queues, "
            "scheduled jobs, or config/env handling"
        ),
        # ⚠️ Every glob is **/-prefixed: repo root is often NOT the Laravel root
        #    (backend/database/... in a monorepo), and PHP+Vue+Helm in one shop
        #    usually means monorepo. Unprefixed, this matches nothing on day one.
        #    `config/**` also fires in secrets-config - deliberate, not a bug.
        "apply_to": "**/database/migrations/**,**/database/seeders/**,**/app/Jobs/**,**/app/Console/**,**/config/**",
        "rules": [
            "**A migration runs against production data, not your seed data.** "
            "How long does it lock the table at real row counts? An `ALTER` that is "
            "instant locally can hold a lock for minutes on a large table.",
            "**Is `down()` honest?** Many are written to satisfy the framework and "
            "would not actually restore anything. If a change is irreversible, say "
            "so in the migration and in `DECISIONS.md` rather than implying a "
            "rollback that does not exist.",
            "**Deploy order matters.** Code expecting a column that ships before the "
            "migration, or a migration that drops a column code still reads, is an "
            "outage in the gap between them. Name the intended order.",
            "**Queue workers run OLD code until restarted.** A job payload changed "
            "on one side of a deploy is deserialised by the other.",
            "**`env()` outside `config/` returns NULL once `config:cache` has run.** That "
            "is the one every Laravel engineer has been bitten by: it works locally, "
            "it works in staging without the cache, and it is null in production. "
            "Read env in config files, read config everywhere else.",
        ],
    },
    {
        "name": "docker-build",
        "traps_scope": "docker",
        "when": (
            "editing Dockerfiles, compose files, base images, or the build/CI "
            "pipeline that produces images"
        ),
        "apply_to": "**/Dockerfile*,**/docker-compose*.yml,.dockerignore,.gitlab-ci.yml,.github/workflows/**",
        "rules": [
            "**A floating tag is not a version.** `:latest` or `:8.2` means the "
            "image that worked yesterday is not the image you get today. If a build "
            "breaks with no code change, look here first.",
            "**Layer order is the build time.** Copying source before installing "
            "dependencies invalidates the dependency layer on every commit.",
            "**What is actually in the image?** `.dockerignore` gaps ship `.env`, "
            "`.git` and local artefacts into a registry someone else can pull.",
            "**Does the pipeline deploy, or only build?** Know which push triggers "
            "what before merging — the most expensive surprise in CI is a job you "
            "did not know was a deploy.",
        ],
    },
    {
        "name": "vue-frontend",
        "traps_scope": "resources",
        "when": (
            "working on the Vue frontend, the asset build, or anything served to "
            "browsers"
        ),
        "apply_to": "**/resources/js/**,**/resources/css/**,**/*.vue,**/vite.config.*,**/webpack.mix.js,**/package.json",
        "rules": [
            "**Build output is cached by browsers and CDNs.** If a fix does not "
            "appear, the question is which cached artefact is being served, not "
            "whether the code is right.",
            "**Env vars are baked in at BUILD time**, not read at runtime — and "
            "anything prefixed for client exposure is public. Never put a secret "
            "behind one.",
            "**Does the backend contract still hold?** A renamed API field breaks "
            "the frontend silently, at runtime, for users rather than in CI.",
        ],
    },
    {
        "name": "secrets-config",
        "traps_scope": "config",
        "when": (
            "handling secrets, credentials, .env files, vault or cluster secrets, "
            "or anything that could commit a credential"
        ),
        "apply_to": "**/.env*,**/secrets*.yaml,**/*secret*.yaml,**/config/**",
        "rules": [
            "⚠️ **A committed secret is compromised even after you delete it.** It "
            "is in the history and on every clone. Rotate first, tidy second.",
            "**Verify with the tool, not with memory.** `git check-ignore <file>` "
            "before assuming a path is excluded.",
            "**Where does this value come from in each environment?** Local `.env`, "
            "CI variable and cluster secret are three different sources that drift "
            "apart quietly.",
            "**Never paste employer code or credentials into a personal AI tool.** "
            "The knowledge layer travels; the code does not.",
        ],
    },
]
