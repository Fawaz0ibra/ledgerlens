# Fonts

The invoice pages are drawn with these files only, never with fonts installed on the machine, so a page
looks the same on every machine and in CI.

| File | Font | SHA-256 |
|---|---|---|
| `IBMPlexSansArabic-Regular.ttf` | IBM Plex Sans Arabic 1.101, Regular | `6f611412270a132bbac838da9259d4c68569b4175f3b3b8fa3fa36a30b56dab9` |
| `IBMPlexSansArabic-Bold.ttf` | IBM Plex Sans Arabic 1.101, Bold | `691e0c891a38637ae6bbdb69700f8042cb0724a137bee615068ffdb92244f61f` |

- **Source:** [google/fonts](https://github.com/google/fonts/tree/5bb28733cec313b63fbd415b574b5ae35c8aa8b8/ofl/ibmplexsansarabic),
  commit `5bb28733cec313b63fbd415b574b5ae35c8aa8b8` (2026-11-08).
- **Licence:** SIL Open Font License 1.1, in [OFL.txt](OFL.txt) (line endings converted to LF, text unchanged).
  The licence allows bundling and redistributing the fonts with software; "Plex" is a Reserved Font Name,
  so a modified version couldn't use it.
- **Coverage, checked with fontTools:** Latin letters and digits, Arabic letters, Arabic-Indic digits
  (٠١٢٣٤٥٦٧٨٩), the Arabic comma and percent sign, and contextual letter forms (a GSUB table). It has no
  glyph for the new Saudi riyal sign (U+20C1), so pages write SAR and ر.س.
