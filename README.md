# VideoAgent

**An agentic video editing system for AI coding agents.**
Give it a raw video, a reference video and an idea. The agent plans the edit, pulls b-roll, images, SFX and music from a reusable component library, renders the result and checks it against quality gates before handing it back.

VideoAgent is not a new engine. It is a **component layer and agent playbook** on top of proven open-source foundations:

| Foundation | License | What VideoAgent uses it for |
|---|---|---|
| [OpenMontage](https://github.com/calesthio/OpenMontage) | AGPL-3.0 | Pipelines, tool registry, provider selection, stock corpus, reference analysis, QA gates, budget control |
| [HyperFrames](https://github.com/heygen-com/hyperframes) | Apache-2.0 | HTML/CSS/GSAP motion graphics rendered as video |
| [Remotion](https://www.remotion.dev) | Remotion License (free for teams of up to 3) | React compositions, word-level captions, Lambda rendering |
| [cinetic](https://github.com/Leonxlnx/cinetic) | MIT | Director skill for designed films: concept, beat grid, technique library, sound, forensics |
| [FFmpeg](https://ffmpeg.org) | LGPL/GPL | Cutting, tone mapping, grading, mixing, encoding |

Works with **Claude Code, Codex, Cursor, Copilot, Windsurf**, and any agent that can read files and run shell commands.

---

## Table of contents

1. [What it does](#what-it-does)
2. [Quick start](#quick-start)
3. [How it works](#how-it-works)
4. [Repository layout](#repository-layout)
5. [The video spec](#the-video-spec)
6. [Component library](#component-library)
7. [Pipelines (templates)](#pipelines-templates)
8. [Render runtimes](#render-runtimes)
9. [Style system](#style-system)
10. [Asset libraries and licensing](#asset-libraries-and-licensing)
11. [Providers and API keys](#providers-and-api-keys)
12. [Quality gates](#quality-gates)
13. [CLI reference](#cli-reference)
14. [Writing a new component](#writing-a-new-component)
15. [Writing a new pipeline](#writing-a-new-pipeline)
16. [Agent contract](#agent-contract)
17. [Platform output profiles](#platform-output-profiles)
18. [Testing](#testing)
19. [Roadmap](#roadmap)
20. [Troubleshooting](#troubleshooting)
21. [License](#license)

---

## Status

v0.1 implements P0-P1 of the roadmap: the `va` CLI, spec planner, compositor (FFmpeg + ASS + image/b-roll overlays), synthesised SFX and music, two-pass mastering, all quality gates, delivery files and the `quiz_game`, `listicle` and `highlight` pipelines. `make demo` renders a 33.5 s quiz reel with zero API keys and passes every gate. Components marked in the tables but not yet in `va components` are on the roadmap.

## What it does

```
INPUT                                  OUTPUT
raw footage (any camera, HDR ok)  ─┐
reference video (URL or file)     ─┼─▶  finished video (mp4)
idea / brief (one paragraph)      ─┘    + thumbnail + captions (.srt)
                                        + post caption + first comment
                                        + QA report
```

- **Reference-driven**: analyses a video you like (pacing, hook, captions, palette, SFX density, structure) and applies that style without copying its content.
- **Footage-first**: edits real footage. Generation is optional, never required.
- **Component-based**: every element (b-roll, sticker, caption, scoreboard, whoosh, music bed, transition) is a reusable component with typed props.
- **Spec-driven**: one YAML file describes the whole video. A fix is a one-line edit and a re-render.
- **Measured finish**: loudness, format, safe zones, sync and visual QA checked before delivery.
- **Free path by default**: works with zero paid API keys (local TTS, stock libraries, synthesised SFX). Paid providers only add options.

---

## Quick start

### Requirements

- Linux or macOS (Windows via WSL2)
- Python 3.11+
- Node.js 22+
- FFmpeg 6+ with libx264, libass and zimg (`zscale`)
- Headless Chromium (HyperFrames/Remotion download one if allowed)
- Optional: NVIDIA GPU for local generation, upscaling and faster ASR

### Install

```bash
git clone https://github.com/narrowaymedia/Hark-studio.git
cd Hark-studio
make setup            # Python venv, OpenMontage deps, Remotion composer, HyperFrames CLI, fonts
cp .env.example .env  # add any keys you have (all optional)
make demo             # renders a sample video with zero keys
```

`make setup` runs:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt               # numpy pillow pyyaml pydantic faster-whisper whisperx
                                              # scenedetect[opencv] mediapipe librosa soundfile
                                              # pyloudnorm pedalboard rembg auto-editor
pip install -r OpenMontage/requirements.txt
(cd OpenMontage/remotion-composer && npm install)
npm i -g hyperframes
npx skills add heygen-com/hyperframes          # HyperFrames agent skills
npx skills add Leonxlnx/cinetic                # cinetic director skill (optional)
```

### Make your first video

Open the repo in your coding agent and say:

```
Here's my footage (inputs/game.mov) and a reel I like
(https://www.instagram.com/reel/XXXX/). Make a 45-second vertical edit:
fast cuts, word-pop captions, a scoreboard for the two teams, b-roll on
each clue, and end with a comment CTA.
```

Or from the CLI:

```bash
va new my-video --pipeline quiz_game
va analyze my-video --footage inputs/game.mov --ref https://www.instagram.com/reel/XXXX/
va plan my-video --idea "two-team clue game, scoreboard, b-roll on clues, comment CTA"
va build my-video
va qa my-video
va deliver my-video
```

---

## How it works

```
             USER (chat / upload)
                    │
                    ▼
   ┌───────────────────────────────────┐
   │  CODING AGENT  (the orchestrator) │  reads AGENTS.md + skills/
   └───────────────────────────────────┘
          │               │              │
          ▼               ▼              ▼
   OpenMontage      VideoAgent       cinetic
   pipelines        pipelines        (designed films)
          │               │
          ▼               ▼
   ┌───────────────────────────────────────────────┐
   │ TOOL REGISTRY  (OpenMontage BaseTool + va/)   │
   │ analysis · broll · images · stickers · text   │
   │ overlays · transitions · sfx · music · voice  │
   │ enhance · qa · deliver                        │
   └───────────────────────────────────────────────┘
          │
          ▼
   RENDER RUNTIMES:  FFmpeg  ·  HyperFrames  ·  Remotion
          │
          ▼
   QA GATES  ──▶  out/deliver/
```

There is no hidden orchestrator. **The coding agent is the orchestrator.** Python provides tools and persistence. Pipelines (YAML) and director skills (Markdown) tell the agent what to do at each stage.

### Stages

| # | Stage | Writes | Gate |
|---|---|---|---|
| 0 | Intake | `brief.yaml` | Format, length, platform, language known |
| 1 | Analyze footage | `analysis/probe.json`, `transcript.json`, `scenes.json`, `faces.json`, `moments.json` | Every candidate moment has a start, end and text |
| 2 | Analyze reference | `analysis/ref_style.json` | Pacing, captions, hook, palette and structure captured |
| 3 | Proposal | `proposal.md` | **User approval** |
| 4 | Plan | `video.yaml` | Duration in target, hook in first 2 s, CTA at end |
| 5 | Assets | `assets/` (b-roll, images, stickers, sfx, music) | **Storyboard approval** (optional) |
| 6 | Build | `build/` (segments, overlays, audio stems) | Safe zones, sync |
| 7 | Compose + master | `out/video.mp4` | Format + loudness |
| 8 | QA | `out/qa/` | All quality gates pass |
| 9 | Deliver | `out/deliver/` | **User approval** to publish |

---

## Repository layout

```
videoagent/
├── OpenMontage/                 # upstream, git submodule (never edited)
├── va/                          # VideoAgent plugin: all custom code
│   ├── tools/                   # BaseTool subclasses, auto-discovered
│   │   ├── analysis/            # probe, transcribe, scenes, faces, moments, ref_style, round_detect
│   │   ├── video/               # segment, tonemap_hlg, reframe_face, punch_zoom, speed_ramp, grade
│   │   ├── broll/               # broll_search, broll_fit, broll_insert, broll_generate
│   │   ├── images/              # image_search, image_gen, cutout_sticker, ken_burns
│   │   ├── text/                # caption, word_pop, hook, kinetic_title, lower_third, tag, cta
│   │   ├── overlays/            # scoreboard, timer, progress_bar, stat_card, info_card
│   │   ├── transitions/         # whip_pan, flash, zoom_through, velocity_cut, shader_wipe
│   │   ├── sfx/                 # sfx_bank, sfx_place, sfx_synth, sfx_generate
│   │   ├── music/               # music_pick, music_synth, beat_grid, duck
│   │   ├── voice/               # voice_chain, tts, denoise, isolate
│   │   ├── qa/                  # format, loudness, safe_zones, sync, black_frames, contact_sheet
│   │   └── deliver/             # thumbnail, post_caption, first_comment, multi_format, split_parts
│   ├── pipeline_defs/           # quiz_game.yaml, listicle.yaml, highlight.yaml, ...
│   ├── skills/                  # director skills per pipeline stage (Markdown)
│   ├── hf_blocks/               # HyperFrames components (HTML + GSAP)
│   ├── remotion/                # extra React components
│   ├── styles/                  # bold_pop.yaml, clean_pro.yaml, warm_doc.yaml
│   ├── schemas/                 # video.schema.json and per-component schemas
│   └── cli.py                   # the `va` command
├── assets/
│   ├── fonts/  sfx/  music/  stickers/  luts/  overlays/  brand/
│   └── manifest.json            # every asset: id, tags, source, license, attribution
├── projects/<name>/             # one folder per video
│   ├── inputs/  analysis/  assets/  build/  out/
│   ├── video.yaml               # the spec
│   └── decisions.jsonl          # every choice with alternatives and reasons
├── AGENTS.md                    # the agent contract (CLAUDE.md, CODEX.md, CURSOR.md point here)
├── Makefile
├── requirements.txt
└── .env.example
```

---

## The video spec

One file describes the whole video. Components are listed on a timeline with their props. Derived values (scores, sync points, durations) are computed, never typed by hand.

```yaml
video:
  name: clue-game-part1
  pipeline: quiz_game
  profile: instagram_reels        # 1080x1920 @30fps, -14 LUFS
  style: bold_pop
  language: en                    # captions language; mixed scripts supported
  runtime: ffmpeg+hyperframes     # locked at proposal; no silent swaps

inputs:
  footage: [inputs/game.mov]
  reference: https://www.instagram.com/reel/XXXX/
  idea: "Two-team clue game, scoreboard, stickers, b-roll on clues, comment CTA"

teams:
  A: {name: TEAM A, side: left,  color: "#E63946"}
  B: {name: TEAM B, side: right, color: "#2D8CFF"}

timeline:
  - Hook:
      text: "Can you guess it in 3 seconds?"
      teaser: auto                  # flashes of the best moments
      seconds: 2.5

  - Round:                          # composite component
      id: r1
      src: footage[0]
      in: 12.4
      out: 21.9
      answer_at: 18.2
      clue: "A talking animal"
      answer: "The answer"
      clue_sticker: {search: "cartoon donkey", style: sticker}
      winner: B                     # A | B | AB | none

  - BRoll:
      query: "dusty road at sunrise"
      at: r1.clue                   # anchors to another component's event
      dur: 1.2
      mode: cutaway                 # cutaway | overlay | split
      source: [pexels, pixabay]

  - Round: {id: r2, src: footage[0], in: 30.1, out: 38.0, answer_at: 35.4,
            clue: "...", answer: "...", winner: A}

  - CTA:
      bonus_clue: "One more clue..."
      countdown: 3
      text: "Comment your answer!"

overlays:                           # always-on layers
  - Scoreboard: {teams: [A, B], position: top, pop_on_change: true}
  - ProgressBar: {position: bottom}

audio:
  voice:  {chain: [highpass_90, denoise, compress_4to1]}
  music:  {mood: upbeat_quiz, bpm: 112, duck_under: voice, gain: -20dB}
  sfx:    {density: medium}         # auto cues from components
  master: {lufs: -14, true_peak: -1.5}

deliver:
  thumbnail:     {frame: best_faces, headline: "WHO WINS?", label: "PART 1"}
  post_caption:  auto
  first_comment: auto
  srt: true
  formats: [9x16]                   # add 1x1, 16x9 for re-layouts
  split: {max_seconds: 60}
```

`Round` is a **composite component**. It expands into `Segment`, `PunchZoom`, `Caption(CLUE)`, `Sticker`, `Timer`, `Caption(ANSWER)`, `Tag`, `ScorePop` and their SFX cues.

---

## Component library

Every component shares one interface, whichever engine draws it:

```python
from va.core import BaseTool, Ctx, Layer, Cue, register   # OpenMontage tools are bridged in va/bridge.py

@register("Sticker")
class Sticker(BaseTool):
    """Pop-in PNG sticker with wobble, bob and drop shadow."""
    class Props(BaseTool.Props):
        image: str                 # asset id or path
        at: float                  # seconds on the video clock
        dur: float = 2.5
        x: int = 540
        y: int = 520
        size: int = 360
        enter: str = "back_out"    # easing token from the style
        wobble: bool = True
        sfx: str | None = "pop"

    engine = "pillow"              # ffmpeg | ass | pillow | hyperframes | remotion

    def layers(self, ctx: Ctx) -> list[Layer]: ...
    def cues(self, ctx: Ctx) -> list[Cue]:
        # sound lands on the frame where scale passes 50%
        return [ctx.cue(self.p.sfx, at=self.p.at + ctx.ease_mid(self.p.enter, 0.32))] if self.p.sfx else []
    def duration(self) -> float:
        return self.p.dur
```

**Rules for every component**

1. Props in, layers + cues out. No hidden file reads; writes only under `build/`.
2. Deterministic: the same props always give the same pixels (seeded randomness).
3. Sync points are computed from the animation, never placed by ear.
4. Colours, fonts and easing come from the style tokens, not raw values.
5. Layers are checked against the profile's safe zones.
6. Every asset used is looked up in `assets/manifest.json` with its license.

### Footage

| Component | Purpose | Engine |
|---|---|---|
| `Segment` | Cut a source range | FFmpeg |
| `TonemapHLG` | Phone HDR (HLG/PQ, BT.2020) to SDR BT.709 | FFmpeg `zscale` + `tonemap=hable` |
| `ReframeFace` | Landscape to vertical following faces | MediaPipe + FFmpeg `crop` |
| `PunchZoom` | Snap zoom on a beat | FFmpeg `scale` expression |
| `SlowZoom` | Ken Burns drift | FFmpeg |
| `SpeedRamp` | Speed up dead air | `setpts` / `atempo` |
| `CutSilence` | Remove silences | auto-editor / `silencedetect` |
| `Freeze` | Freeze-frame reveal | `tpad` |
| `ColorGrade` | LUT, saturation, contrast | `lut3d`, `eq` |
| `Stabilize` | Smooth handheld | `vidstab` |
| `Denoise` | Low-light grain | `hqdn3d` / `nlmeans` |
| `Upscale` | Low-res sources | Real-ESRGAN |
| `FaceRestore` | Soft faces | CodeFormer / GFPGAN |
| `SplitScreen` / `PiP` | Side by side, reaction cam | FFmpeg `xstack` / `overlay` |

### B-roll

| Component | Purpose | Source |
|---|---|---|
| `BRollSearch` | Find clips by meaning (CLIP-ranked) | Pexels, Pixabay, Archive.org, NASA, Wikimedia Commons |
| `BRollFit` | Trim, crop to aspect, grade-match the main footage | FFmpeg |
| `BRollInsert` | Cutaway, overlay or split-screen insert | Timeline |
| `BRollGenerate` | AI clip when stock has nothing | Kling, Veo, Grok Imagine, Seedance, Runway, local WAN/LTX (optional) |
| `ImageToMotion` | Still to moving shot | Ken Burns or image-to-video |
| `BRollLibrary` | Reuse saved clips across projects | `assets/manifest.json` |

### Images and stickers

| Component | Purpose |
|---|---|
| `ImageSearch` | Stock stills from Pexels, Unsplash, Pixabay, Wikimedia |
| `ImageGen` | FLUX, Imagen, GPT Image, Grok, Nano Banana, Gemini, local Stable Diffusion |
| `CutoutSticker` | rembg background removal → transparent sticker with outline + shadow |
| `StyledSticker` | Illustrated / anime / flat sticker generated once, cached |
| `KenBurns` | Animated still |
| `PhotoFrame` | Polaroid or framed photo pop-in |
| `Thumbnail` | Real-frame cover: best faces, grade, headline, label, grid-safe crop |

### Text and captions

| Component | Purpose | Engine |
|---|---|---|
| `Caption` | Labelled caption bar (e.g. CLUE / ANSWER) | ASS |
| `WordPop` | Word-by-word karaoke captions from word timestamps | ASS `\k` / Remotion captions |
| `Hook` | Opening question + teaser flashes | ASS + FFmpeg |
| `KineticTitle` | Fragment-style text (a few words at a time) | HyperFrames |
| `LowerThird` | Name / role bar | HyperFrames |
| `Tag` | Stamp: CORRECT, WRONG, NO ANSWER, +1 | ASS |
| `CTA` | Bonus clue / countdown / comment prompt on blurred background | ASS + FFmpeg |
| `SRTExport` | .srt / .vtt files | Built in |

### Overlays and data

| Component | Purpose |
|---|---|
| `Scoreboard` | Team scores computed from winners; pop and glow on change |
| `ScorePop` | "+1" flying into the score box |
| `Timer` | Countdown bar with ticks |
| `ProgressBar` | Video progress line |
| `InfoCard` | Title / subtitle / fields card (products, listings, facts) |
| `StatCard` / `DataChart` | Animated numbers and charts |
| `FollowCTA` | Platform follow block |
| `Leaderboard` | Multi-entry rankings |

### Transitions

| Component | Feel |
|---|---|
| `HardCut` | Default for most cuts |
| `WhipPan` | Energetic; whoosh peak lands on the cut frame |
| `Flash` | Reveal (HyperFrames `flash-through-white`) |
| `ZoomThrough` | Push into the next scene |
| `VelocityCut` | Momentum carried through the cut (exit accelerates 16-24 f, entry decelerates 45-90 f) |
| `MatchCut` | Shape or colour carries across |
| `ShaderWipe` | HyperFrames shader transitions; use sparingly |

### Sound effects

| Component | Purpose |
|---|---|
| `SFXBank` | Categorised library: ding, correct, wrong/buzzer, whoosh (short/long), pop, coin, tick, drumroll, impact, riser, scratch, applause, laugh, cheer, shutter, notification, typing, swoosh-text |
| `SFXPlace` | Places each sound on its computed sync frame |
| `SFXSynth` | NumPy-synthesised fallback, zero dependencies |
| `SFXGenerate` | Text-to-SFX (ElevenLabs, optional) |
| `EarshotKit` | Measured, code-designed SFX takes (via cinetic) |

### Music and voice

| Component | Purpose |
|---|---|
| `MusicPick` | Search by mood + BPM in the library or providers |
| `MusicSynth` | Built-in loop bed, zero dependencies |
| `BeatGrid` | `b(bar, beat, sub)` frame helper for cutting on the beat |
| `Duck` | Sidechain the music under the voice |
| `VoiceChain` | Highpass → denoise (RNNoise) → compress → optional Demucs isolation |
| `TTS` | Piper (free, local), Google TTS, OpenAI, ElevenLabs |
| `Master` | `loudnorm` to the profile target |

### Analysis

| Component | Purpose |
|---|---|
| `Probe` | Resolution, fps, rotation, HDR transfer, audio layout |
| `Transcribe` | WhisperX / faster-whisper with word timestamps, multilingual |
| `SceneDetect` | Shot boundaries (PySceneDetect) |
| `Faces` | Per-frame face boxes (MediaPipe) |
| `Moments` | Laughter, applause, loudness and keyword peaks |
| `RoundDetect` | Question → answer → reaction patterns in game footage |
| `RefStyle` | Reference video profile (see below) |
| `VideoUnderstand` | CLIP / BLIP frame descriptions |

`RefStyle` output:

```json
{
  "duration": 42.0,
  "avg_shot_len": 1.6,
  "hook": {"type": "question_text+teaser", "seconds": 2.0},
  "captions": {"style": "word_pop", "position": "center_low", "case": "upper", "font_feel": "bold condensed"},
  "palette": ["#111111", "#FFD400", "#FFFFFF"],
  "zoom_events_per_10s": 3,
  "sfx_events_per_10s": 4,
  "music": {"present": true, "bpm": 118, "ducked": true},
  "structure": ["hook", "rounds", "cta"]
}
```

### Delivery

| Component | Purpose |
|---|---|
| `Thumbnail` | Cover image from a real frame |
| `PostCaption` | Platform caption: hook line, summary, CTA, hashtags (no spoilers) |
| `FirstComment` | Engagement prompt to pin |
| `MultiFormat` | 9:16, 1:1 and 16:9 re-layouts from one spec (re-laid out, not cropped) |
| `SplitParts` | Split long videos into parts with cliffhangers |
| `Publish` | Hand-off to a scheduler (Buffer, platform APIs), only after user approval |

---

## Pipelines (templates)

| Pipeline | Source | Structure | Main components |
|---|---|---|---|
| `quiz_game` | VideoAgent | Hook → Rounds × N → Score → CTA | Round, Scoreboard, Sticker, Timer, Tag, CTA |
| `listicle` | VideoAgent | Hook → InfoCard × N → CTA | InfoCard, WordPop, BRoll, ProgressBar, TTS |
| `highlight` | VideoAgent | Ranked moments → beat-cut montage | Moments, BeatGrid, VelocityCut, MusicPick |
| `hybrid` | OpenMontage | Own footage + stock/AI support visuals | BRoll, ImageGen, captions |
| `talking_head` | OpenMontage | Cut silences, captions, zooms | CutSilence, WordPop, PunchZoom, LowerThird |
| `clip_factory` | OpenMontage | Long video → ranked short clips | Moments, ReframeFace, WordPop |
| `documentary_montage` | OpenMontage | Real-footage b-roll essay | BRollSearch corpus, MusicPick |
| `animated_explainer` | OpenMontage | Narrated explainer from images/scenes | TTS, ImageGen, Remotion scenes |
| `localization` | OpenMontage | Subtitle / dub into other languages | Transcribe, TTS, SRT |
| `launch_film` | cinetic | Concept → brand → acts → sound → master | HyperFrames / Remotion + earshot |

A pipeline is a YAML manifest plus one director skill per stage:

```yaml
# va/pipeline_defs/quiz_game.yaml
name: quiz_game
description: Footage of a game with rounds and teams, cut into a scored short.
stages:
  - id: analyze
    tools: [Probe, Transcribe, SceneDetect, Faces, RoundDetect, Moments, RefStyle]
    skill: skills/quiz_game/analyze.md
  - id: proposal
    skill: skills/quiz_game/proposal.md
    gate: user_approval
  - id: plan
    output: video.yaml
    skill: skills/quiz_game/plan.md
    checks: [duration_target, hook_first_2s, cta_last]
  - id: assets
    tools: [ImageSearch, ImageGen, CutoutSticker, BRollSearch, BRollFit, SFXBank, MusicPick]
    gate: storyboard_optional
  - id: build
    runtime: ffmpeg+hyperframes
  - id: qa
    tools: [qa.*]
  - id: deliver
    tools: [Thumbnail, PostCaption, FirstComment, SplitParts]
    gate: user_approval_to_publish
defaults:
  profile: instagram_reels
  style: bold_pop
  split: {max_seconds: 60}
```

---

## Render runtimes

| Runtime | Best for | Speed | Notes |
|---|---|---|---|
| **FFmpeg** | Footage, cuts, grade, zoom, tone map, mix, encode | Fastest | Always the base layer and final encoder |
| **ASS / libass** | Text, shapes, simple motion | Very fast | Burned in with the `subtitles` filter |
| **Pillow** | Bitmap stickers, custom per-frame drawing | Medium | RGBA frames piped to FFmpeg stdin |
| **HyperFrames** | Rich motion graphics, shader transitions, catalog blocks | Slower | Renders transparent overlays composited by FFmpeg |
| **Remotion** | React components, word captions, Lambda batch | Slower | Check the license for teams of 4+ |

**Hybrid pattern (default):** FFmpeg + ASS + Pillow for the bulk; HyperFrames or Remotion only for hero graphics, rendered as alpha video:

```bash
npx hyperframes render va/hf_blocks/scoreboard --format mov-alpha -o build/hf/scoreboard.mov
ffmpeg -i build/body.mp4 -i build/hf/scoreboard.mov -filter_complex "[0][1]overlay=0:0" ...
```

A HyperFrames block is HTML with timing attributes:

```html
<div id="stage" data-composition-id="scoreboard" data-width="1080" data-height="1920">
  <div id="board" class="clip" data-start="0" data-duration="60" data-track-index="1">
    <span id="a">0</span><span id="b">0</span>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3/dist/gsap.min.js"></script>
  <script>
    const tl = gsap.timeline({ paused: true });
    // score events injected from video.yaml at build time
    window.__timelines = { scoreboard: tl };
  </script>
</div>
```

The compositor (`build` stage):

```
1. Segments    ffmpeg per segment (tonemap, reframe, zoom, grade)   → build/seg/*.mp4   [parallel]
2. Body        concat demuxer                                        → build/body.mp4
3. ASS layer   all ASS components                                    → build/overlay.ass
4. Pillow      RGBA frames streamed to ffmpeg stdin
5. HF/Remotion hero blocks                                           → build/hf/*.mov (alpha)
6. Audio       SFX cues → sfx.wav, music → music.wav, voice chain
7. Composite   [body]→overlay(pillow)→overlay(hf)→subtitles(ass)→[v]
               [voice][sfx][music ducked]→amix→loudnorm→[a]
               -c:v libx264 -crf 20 -pix_fmt yuv420p -r 30
               -c:a aac -b:a 192k -ar 48000 -movflags +faststart
```

---

## Style system

A style is a YAML token file. Components read tokens, never raw values.

```yaml
# va/styles/bold_pop.yaml
fonts:
  display: Anton
  fun: Bangers
  body: Montserrat
  fallback: [Noto Sans, Noto Sans Tamil, Noto Sans Devanagari]
colors:
  ink: "#111111"
  paper: "#FFFFFF"
  accent: "#FFD400"
  team_a: "#E63946"
  team_b: "#2D8CFF"
motion:
  enter: back_out
  exit: expo_in
  punch_zoom: 0.16
captions: {style: word_pop, case: upper, stroke: 6, position: center_low}
sfx: {density: medium, kit: playful}
music: {mood: upbeat, bpm: [105, 125]}
grade: {lut: punchy.cube, saturation: 1.12}
```

Included styles: `bold_pop` (games, fun shorts), `clean_pro` (business, tutorials), `warm_doc` (events, documentary).

**Always-on rules**

- Keep text and stickers out of platform UI zones (see profiles).
- Thumbnails come from real frames unless the brief says otherwise.
- Restraint: one sound per text fragment, a big hit only for the main reveal.
- Generic "AI look" bans (from cinetic): no glow/neon halos, multi-hue gradients, glassmorphism, lens flares, code rain or sparkles-for-AI unless the user's brand calls for them. A supplied brand always wins.

---

## Asset libraries and licensing

`assets/manifest.json` records every reusable asset:

```json
{
  "id": "sfx/whoosh_short_03",
  "path": "assets/sfx/whoosh_short_03.wav",
  "tags": ["whoosh", "transition", "short"],
  "duration": 0.42,
  "sync_point": 0.18,
  "source": "synth",
  "license": "own",
  "attribution": null
}
```

| Library | Starter size | Sources (license) |
|---|---|---|
| SFX | 60+ sounds in 18 categories | Own synth, earshot, Pixabay (Pixabay License), Freesound (CC0 only), Mixkit (Mixkit License) |
| Music | 20 beds by mood and BPM | Own synth, Pixabay Music, Free Music Archive (CC BY / CC0), YouTube Audio Library |
| B-roll cache | Grows per project | Pexels, Pixabay, Archive.org (PD), NASA (PD), Wikimedia (per file) |
| Images | Grows per project | Pexels, Unsplash, Pixabay, Wikimedia, generated |
| Stickers | Grows per project | Generated or rembg cutouts |
| LUTs | 6 | Own |
| Fonts | 8 families | Google Fonts (OFL) |

Rules: only CC0, public domain or platform licenses that allow commercial reuse; every file logged with source and attribution; the QA gate fails a render that uses an unlogged asset.

---

## Providers and API keys

All keys are optional. Keep them in `.env` (or a secret manager); never commit them.

```bash
# Free stock
PEXELS_API_KEY=
PIXABAY_API_KEY=
UNSPLASH_ACCESS_KEY=
FREESOUND_API_KEY=

# Generation gateways (optional, paid per use)
FAL_KEY=                # FLUX images, Kling / Veo / MiniMax video
XAI_API_KEY=            # Grok image + video
GOOGLE_API_KEY=         # Imagen, Gemini, Google TTS
OPENAI_API_KEY=         # GPT Image, TTS
KLING_API_KEY=
RUNWAY_API_KEY=
ELEVENLABS_API_KEY=     # TTS, SFX, music
SUNO_API_KEY=           # music

# Local GPU (optional)
VIDEO_GEN_LOCAL_ENABLED=false
VIDEO_GEN_LOCAL_MODEL=wan2.2-ti2v-5b

# Budget
BUDGET_MODE=cap         # observe | warn | cap
BUDGET_TOTAL_USD=10
BUDGET_APPROVE_ABOVE_USD=0.50
```

Provider choice uses OpenMontage's scored selector (task fit, quality, control, reliability, cost, latency, continuity), and every choice is logged in `decisions.jsonl`.

---

## Quality gates

| Gate | Pass condition |
|---|---|
| Format | Matches the profile (resolution, fps, H.264 yuv420p, AAC 48 kHz, faststart) |
| Loudness | Profile target ±1 LU, true peak ≤ -1.5 dBTP |
| Data integrity | Displayed values (scores, counts) equal values derived from the spec |
| Safe zones | No text or sticker in the platform UI zones |
| Black / frozen frames | None unintended (`blackdetect`, `freezedetect`) |
| Sync | Each SFX within 1 frame of its visual event |
| Slideshow risk | OpenMontage score below threshold |
| Licensing | Every asset in the manifest with a valid license |
| Duration | Within the profile / pipeline target |
| Visual review | Contact sheet reviewed by the agent before delivery |

```bash
# contact sheet, 1 frame per second
ffmpeg -i out/video.mp4 -vf "fps=1,scale=270:-1,tile=6x5" -frames:v 1 out/qa/contact.jpg
# loudness
ffmpeg -i out/video.mp4 -af ebur128=peak=true -f null -
```

---

## CLI reference

```bash
va new <name> --pipeline <pipeline>                 # scaffold projects/<name>/
va analyze <name> --footage <files> [--ref <url|file>]
va plan <name> --idea "<text>"                      # writes proposal.md and video.yaml
va assets <name>                                    # fetch/generate b-roll, images, stickers, sfx, music
va build <name> [--part N] [--preview]              # --preview = half-res, fast
va qa <name>                                        # run all gates, write out/qa/
va deliver <name>                                   # thumbnail, captions, srt, formats
va edit <name> "<instruction>"                      # agent edits video.yaml, then rebuilds
va lib add <file> --tags a,b --license CC0 --source <url>
va lib search sfx "whoosh short"
va components                                       # list every registered component and its props
va doctor                                           # check ffmpeg, node, chromium, fonts, keys
```

---

## Writing a new component

1. Create `va/tools/<category>/<name>.py` with a `BaseTool` subclass and `@register("<Name>")`.
2. Declare typed `Props`. Read colours, fonts and easing from `ctx.style`.
3. Implement `layers()`, `cues()` and `duration()`.
4. Add a JSON schema in `va/schemas/` (generated from `Props` with `va schema`).
5. Add a usage note in `va/skills/components/<name>.md`: when to use it, when not to, and its defaults.
6. Add a snapshot test: render 3 seconds on a test clip and compare the contact sheet.

The registry auto-discovers it; `va components` lists it.

## Writing a new pipeline

1. Add `va/pipeline_defs/<name>.yaml` (stages, tools, gates, defaults).
2. Add a director skill per stage in `va/skills/<name>/`.
3. Reuse existing components; add new ones only when the behaviour is new.
4. Add a 20-second smoke test clip and its expected outputs.

---

## Agent contract

`AGENTS.md` (mirrored by `CLAUDE.md`, `CODEX.md`, `CURSOR.md`) tells any coding agent:

1. Pick a pipeline first, then read its manifest and the stage skill before calling tools.
2. Never improvise outside the pipeline; propose a new component instead.
3. Stop at every approval gate and wait for the user.
4. Lock the render runtime at proposal; never swap silently.
5. Never spend above the budget threshold without approval.
6. Never publish without explicit approval.
7. Log every decision with alternatives and reasons in `decisions.jsonl`.
8. Never present a render that failed QA.
9. Write renders to local temp storage first, then copy (some network filesystems corrupt the mp4 trailer).

---

## Platform output profiles

| Profile | Size | FPS | Loudness | Safe zone (avoid) |
|---|---|---|---|---|
| `instagram_reels` | 1080×1920 | 30 | -14 LUFS | top 220 px, bottom 380 px, right 120 px; cover grid shows the centre 3:4 |
| `tiktok` | 1080×1920 | 30 | -14 LUFS | top 160 px, bottom 420 px, right 140 px |
| `youtube_shorts` | 1080×1920 | 30 | -14 LUFS | top 200 px, bottom 360 px |
| `youtube` | 1920×1080 | 30/60 | -14 LUFS | standard title-safe |
| `square` | 1080×1080 | 30 | -14 LUFS | 60 px margins |
| `linkedin` | 1920×1080 | 30 | -14 LUFS | standard |

---

## Testing

```bash
make test-contracts    # every component's props validate against its schema
make test-snapshots    # 3-second renders compared by contact sheet
make test-pipelines    # 20-second smoke clip per pipeline
make test-qa           # the gates catch known-bad fixtures (black frames, clipping, unsafe text)
```

Golden tests re-render reference projects from their specs and must match timing (±2 frames), loudness (±0.5 LU) and derived data exactly.

---

## Roadmap

| Phase | Deliverable |
|---|---|
| P0 Setup | OpenMontage submodule, HyperFrames, Remotion composer, cinetic, `va doctor`, `make demo` |
| P1 Core components | Footage, text, overlays, SFX synth, music synth, master, thumbnail |
| P2 Libraries | SFX bank, music beds, LUTs, fonts, manifest with licenses |
| P3 B-roll + images | Stock search, fit, insert, generation fallback, stickers |
| P4 Analysis | Moments, RoundDetect, RefStyle |
| P5 HyperFrames blocks | Scoreboard, InfoCard, KineticTitle, LowerThird, FollowCTA |
| P6 Pipelines | quiz_game, listicle, highlight + director skills |
| P7 QA + delivery | All gates, captions, multi-format, split parts |
| P8 Agent integration | AGENTS.md, skills for Claude Code / Codex / Cursor, chat-to-video flow |
| P9 Batch | Data-driven batch renders (one spec template, many rows) |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Washed-out or grey colours from phone footage | Source is HDR; make sure `TonemapHLG` runs (`va analyze` flags `arib-std-b67` / `smpte2084`) |
| `No such filter: zscale` | Install an FFmpeg build with zimg |
| Captions render in the wrong font | Pass `fontsdir=assets/fonts` to the `subtitles` filter; run `va doctor` |
| HyperFrames render hangs | Node must be 22+; set `CHROMIUM_PATH`; run `npx hyperframes lint` |
| mp4 won't play after copy | Render to `/tmp` first, then copy; keep `-movflags +faststart` |
| Music drowns the voice | Raise the `duck` ratio or lower `music.gain`; check the voice chain |
| Wrong words in captions | Use WhisperX large-v3 with the correct language; fix words in `transcript.json` and rebuild |
| Render too slow | `va build --preview`; render HyperFrames blocks once and cache; parallel segments |

---

## License

VideoAgent's own code (`va/`) is MIT.
It depends on **OpenMontage (AGPL-3.0)**: if you offer a modified version as a network service, you must publish the source. HyperFrames is Apache-2.0, cinetic is MIT, and Remotion has its own license (free for individuals and companies of up to 3 people). Check each asset's license in `assets/manifest.json` before commercial use.
