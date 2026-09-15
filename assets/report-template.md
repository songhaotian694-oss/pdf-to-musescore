# PDF to MuseScore processing report

Status: {{STATUS}}

Source PDF: {{INPUT}}

Error / action needed: {{ERROR}}

See `report.json` for `outputMode`, `draftUsable`, `acceptancePassed`, and separate technical/content/playback/layout results. `editable_draft_*` means `score.mscz` is a correction draft, never an accepted result. `preflight.json` and `source-thumbnails/` cover ALL source pages. `selection.json` records source SHA256 and selected pages. `content-musicxml.json` checks per-part expectations; `structure-verify-*/content-proof.json` and thumbnails check ALL proof pages.

`recognitionAttempts` records original and optional 400 DPI grayscale Audiveris attempts. `selectedRecognitionProfile` identifies the chosen MusicXML. `qualityPenalty` compares reviewed structure only and is not a note-accuracy percentage.

`conversion.log` records commands, exit codes and durations. Separate stdout/stderr logs can contain score text and local paths; review before sharing.

Playback is a separate mandatory gate: `playback-assignment.json` records intended instruments; `verification.playbackValidation` in `report.json` and `playback-verify-*.json` check saved MSCZ routing and actual note-on programs in freshly exported MIDI. A delivered `score.mid` is checked too. `failed_playback_validation` means the draft is not accepted. MIDI verification does not replace listening.

## Manual correction checklist

`layout-assignment.json` records the selected reflow/source break policy; `verification.layoutValidation` checks persistence after saving. Review short last systems, sparse last pages, spacing and practical page turns visually even when this check passes.

{{WARNINGS}}

- Compare every source page with the proof PDF; ensure no pages, systems or movements are missing.
- Check meter and incomplete bars, clefs, key signatures and accidentals.
- Check note/rest durations, dots, tuplets, slurs and ties across bars.
- Check lyrics, multiple voices, cross-staff notes and synchronization.
- Check repeats, endings, tempo, dynamics and playback.

Successful file validation does not establish musical accuracy. Keep the original PDF, OMR and MusicXML for correction.
