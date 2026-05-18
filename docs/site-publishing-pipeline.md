# Verdify Site Publishing Pipeline

This is the operator trace for publishing `lab.verdify.ai` from Obsidian content.

## Source of Truth

Hand-authored website content lives in:

```text
/mnt/iris/verdify-vault/website
```

Quartz reads that same tree through:

```text
/srv/verdify/verdify-site/content -> /mnt/iris/verdify-vault/website
```

Generated pages, such as `/forecast`, `/data/forecast`, `/plans/YYYY-MM-DD`,
`/plans/index`, `/data/plans`, `/reference/lessons`, crop profiles, zone pages,
equipment blocks, and public sample datasets are written into the same website
tree by generator scripts. Do not hand-edit generated blocks or pages unless you
expect the generator to overwrite them later.

Production refreshes use one entry point:

```bash
/srv/verdify/scripts/publish-site-content.sh --reason manual
```

Planner publishes, forecast-page refreshes, and manual full refreshes all call
that script. It regenerates the daily plan, forecast page, plan indexes,
lessons, Baseline vs Iris, equipment blocks, zone pages, crop profiles, public
sample CSVs, and planner static context before rebuilding the site.

Some public routes are aliases that must stay byte-identical because the nav and
story pages link to the `/data/...` route while older canonical pages still
exist:

```text
forecast/index.md              == data/forecast/index.md
plans/index.md                 == data/plans/index.md
evidence/baseline-vs-iris.md   == data/baseline-vs-iris.md
```

`make site-doctor` enforces those alias pairs, checks forecast freshness from
`last_updated`, verifies that both plan indexes list the newest
`plans/YYYY-MM-DD.md` page first, rejects duplicate route owners, and rejects
retired source paths such as the old `intelligence/`, `slack/`, and duplicate
top-level article copies. A stale generated route is a release-blocking
site-doctor error, not a visual cleanup task.

## Publish Flow

```text
Obsidian on Mac
  -> Syncthing
  -> /mnt/iris/verdify-vault/website
  -> publish-site-content.sh for generated refreshes
  -> verdify-site-poll.timer for hand-authored edits
  -> scripts/site-poll-and-rebuild.sh
  -> scripts/rebuild-site.sh
  -> npx quartz build --output /srv/verdify/verdify-site/.builds/public.*
  -> rsync staged output into /srv/verdify/verdify-site/public
  -> /srv/verdify/verdify-site/public
  -> verdify-site nginx stays running
  -> Traefik / Cloudflare / lab.verdify.ai
```

## Low-Downtime Publish

Quartz clears its output directory before emitting a new site. Building directly
into the live `public/` directory creates a short window where nginx can serve
404s for normal pages. Verdify now avoids that by building into a temporary
staging directory under:

```text
/srv/verdify/verdify-site/.builds/public.*
```

Only after Quartz succeeds and `index.html` exists does the rebuild script sync
the staged output into the live public directory:

```text
/srv/verdify/verdify-site/public
```

The sync uses delayed deletes, so existing pages stay available while new files
copy into place. The `verdify-site` nginx container is left running for normal
content changes. It is reloaded only when `site/nginx.conf` changes, with a
container restart as the fallback if reload fails.

## Change Detection

The poll timer fires every 10 seconds:

```bash
systemctl status verdify-site-poll.timer
```

The poller does **not** rely on `find -newer` anymore. Syncthing can preserve
the source file modification time, which means a real Mac/Obsidian edit can
arrive with an mtime older than the last build marker. The poller now compares a
metadata signature for the whole website tree:

- relative path;
- file size;
- mtime;
- ctime.

That catches additions, deletions, renames, and preserved-mtime Syncthing
updates without hashing large image contents every 10 seconds.

State files:

```text
/var/local/verdify/state/site-content.signature  # last successfully built tree signature
/var/local/verdify/state/site-build-last-run     # human-readable last successful build marker
/srv/verdify/state/site-build.log                # Quartz build/publish log
/srv/verdify/verdify-site/.builds/               # temporary staged build output
```

The signature is updated only after a successful build. If Quartz fails, the old
signature remains and the next poll retries.

## Normal Checks

Use this first when an Obsidian edit does not show up:

```bash
make site-publish-status
```

Then check the build log:

```bash
tail -80 /srv/verdify/state/site-build.log
```

Run a manual rebuild:

```bash
make site-rebuild
```

Regenerate every generated public page and rebuild:

```bash
/srv/verdify/scripts/publish-site-content.sh --reason manual
```

Validate the built site:

```bash
make site-doctor
```

For generated planning and forecast pages, also confirm the nav-facing routes:

```bash
curl -fsSL https://lab.verdify.ai/data/forecast/ | rg '05-[0-9]{2} [0-9]{2}:00'
curl -fsSL https://lab.verdify.ai/data/plans/ | rg "$(date +%Y-%m-%d)"
```

## Debugging Mac/Syncthing Edits

If `make site-publish-status` shows `pending rebuild: no` and the public site
is still stale, first confirm the edit actually reached the VM:

```bash
rg 'text you edited' /mnt/iris/verdify-vault/website
stat /mnt/iris/verdify-vault/website/path/to/page.md
```

If the text is missing from the VM, the issue is before Verdify publishing:
Obsidian save, Syncthing folder mapping, Syncthing conflict resolution, or the
NAS/NFS mount.

If the text exists in the VM but not in `/srv/verdify/verdify-site/public`,
the issue is Quartz build/publish. Run:

```bash
make site-rebuild
make site-doctor
```

If the generated HTML is correct locally but `lab.verdify.ai` is stale, the issue is
serving/cache. Check:

```bash
curl -I https://lab.verdify.ai/
```

Only restart `verdify-site` if nginx is serving errors while
`/srv/verdify/verdify-site/public/index.html` exists, or if the build log reports
that reload failed.
