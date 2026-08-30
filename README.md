# valfridsson.net

Källkod för [valfridsson.net](https://valfridsson.net/), byggd med
[Hugo](https://gohugo.io/) och driftsatt på GitHub Pages via GitHub
Actions.

Sajten samlar fyra tidigare separata sidor under samma domän:

- [`/`](https://valfridsson.net/) — Daniels egen kontaktsida
- [`/cina/`](https://valfridsson.net/cina/) — konstportfölj för
  Cina Jeppsson
- [`/ivan/`](https://valfridsson.net/ivan/) — familjesida för Ivan &
  Elsie Valfridsson
- [`/ivan-old/`](https://valfridsson.net/ivan-old/) — äldre version av
  Ivans sida, bevarad för sitt stora fotoarkiv
- [`/masten/`](https://valfridsson.net/masten/) — MASTEN Socialt
  Center Tyresö

Sajterna byggdes ursprungligen med Sandvox (nedlagt program) respektive
äldre FrontPage-HTML och migrerades till Hugo under 2026.

## Kom igång lokalt

Kräver [Hugo Extended](https://gohugo.io/installation/) och
[Node.js](https://nodejs.org/) (för sökindexeringen).

```sh
hugo server -D    # lokal utvecklingsserver, inkluderar utkast (draft)
hugo --minify     # produktionsbygge till public/, samma som körs i CI
```

## Innehåll

Allt innehåll ligger som Markdown under `content/`, ett bundle per sida
(en `index.sv.md` eller `_index.sv.md` plus eventuella bilder/PDF:er i
samma mapp). Sätt `draft: true` i en sidas frontmatter för att dölja
den från publicerade bygget.

## Driftsättning

Varje push till `main` triggar `.github/workflows/hugo.yml`, som bygger
sajten med Hugo, genererar sökindex med [Pagefind](https://pagefind.app/)
och publicerar via `actions/deploy-pages`.

## Mer teknisk dokumentation

Se [`CLAUDE.md`](CLAUDE.md) för arkitekturbeslut, konventioner och en
detaljerad logg över migreringsbeslut (vad som medvetet inte migrerades,
kända avvikelser m.m.).
