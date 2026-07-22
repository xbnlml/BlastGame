---
name: music
description: "Music and audio — songwriting craft, AI music generation (HeartMuLa), audio analysis (spectrograms, features), and Suno AI prompt engineering."
version: 1.0.0
author: Hermes Agent
tags: [music, songwriting, audio, music-generation, spectrogram, lyrics, heartmula, suno, prompt-engineering]
platforms: [linux, macos, windows]
triggers:
  - writing a song
  - song lyrics
  - music prompt
  - suno prompt
  - parody song
  - adapting a song
  - AI music generation
  - audio analysis
  - spectrogram generation
  - HeartMuLa
  - music generation model
---

# Music — Songwriting, Generation & Analysis

Three facets of music production in one skill. Pick the section that matches your task.

| Section | When to Use |
|---------|-------------|
| **Songwriting & AI Prompts** | Writing lyrics, crafting Suno AI music prompts, parody adaptation |
| **Open-Source Music Generation** | Generating full songs locally with HeartMuLa from lyrics + tags |
| **Audio Analysis** | Creating spectrograms, visualizing audio features (mel, chroma, MFCC) |

---

## Section 1: Songwriting Craft & AI Music Prompts

### Song Structure (Pick One or Invent Your Own)

Common skeletons — mix, modify, or throw out as needed:

```
ABABCB  Verse/Chorus/Verse/Chorus/Bridge/Chorus    (most pop/rock)
AABA    Verse/Verse/Bridge/Verse (refrain-based)    (jazz standards, ballads)
ABAB    Verse/Chorus alternating                    (simple, direct)
AAA     Verse/Verse/Verse (strophic, no chorus)     (folk, storytelling)
```

The six building blocks:
- Intro      — set the mood, pull the listener in
- Verse      — the story, the details, the world-building
- Pre-Chorus — optional tension ramp before the payoff
- Chorus     — the emotional core, the part people remember
- Bridge     — a detour, a shift in perspective or key
- Outro      — the farewell, can echo or subvert the rest

### Rhyme, Meter, and Sound

**Rhyme types** (from tight to loose):
- Perfect: lean/mean
- Family: crate/braid
- Assonance: had/glass (same vowels, different endings)
- Consonance: scene/when (different vowels, similar endings)
- Near/slant: enough to suggest connection without locking it down

Mix them. All perfect rhymes can sound like a nursery rhyme.

**Meter:** The rhythm of stressed vs unstressed syllables. Matching syllable counts between parallel lines helps singability. Say it out loud — if you stumble, the meter needs work.

### Emotional Arc and Dynamics

Think of a song as a journey, not a flat road:

```
Intro: 2-3  |  Verse: 5-6  |  Pre-Chorus: 7
Chorus: 8-9  |  Bridge: varies  |  Final Chorus: 9-10
```

The most powerful dynamic trick: CONTRAST. Whisper before a scream hits harder than just screaming. Silence is an instrument.

### Writing Lyrics That Work

**Show, don't tell** (usually): "I was sad" = flat. "Your hoodie's still on the hook by the door" = alive.

**The hook:** The line people remember, hum, repeat. Usually the title or core phrase.

**Avoid:** Cliches on autopilot, forcing word order to hit a rhyme, same energy in every section.

### Parody and Adaptation

When rewriting an existing song with new lyrics:

1. Map the original's structure: count syllables per line, mark the rhyme scheme, identify stressed syllables
2. Fit new words: match stressed syllables to the same beats, total syllable count can flex by 1-2 unstressed syllables
3. On long held notes, try to match the vowel sound of the original
4. Sing your new words over the original — if you stumble, revise

### Suno AI Prompt Engineering

**Style/Genre Description Formula:** Genre + Mood + Era + Instruments + Vocal Style + Production + Dynamics

```text
GOOD: "Cinematic orchestral spy thriller, 1960s Cold War era, smoky
       sultry female vocalist, big band jazz, brass section with
       trumpets and french horns, sweeping strings, minor key,
       vintage analog warmth"
```

**Metatags** (place in [brackets] inside lyrics field):
- Structure: `[Intro]`, `[Verse]`, `[Chorus]`, `[Bridge]`, `[Outro]`
- Vocal: `[Whispered]`, `[Belted]`, `[Falsetto]`, `[Harmonies]`
- Dynamics: `[High Energy]`, `[Explosive]`, `[Building Energy]`
- Atmosphere: `[Melancholic]`, `[Euphoric]`, `[Dark Atmosphere]`

**Phonetic tricks for AI singers:** Spell words as they sound ("through" → "thru"), use ALL CAPS for louder, hyphens for sustained notes ("lo-o-o-ove").

---

## Section 2: Open-Source Music Generation (HeartMuLa)

HeartMuLa is an open-source music foundation model (Apache-2.0) that generates music conditioned on lyrics and tags, with multilingual support. Comparable to Suno for open-source.

### Hardware Requirements
- **Minimum:** 8GB VRAM with `--lazy_load true` (loads/unloads models sequentially)
- **Recommended:** 16GB+ VRAM for comfortable single-GPU usage
- 3B model with lazy_load peaks at ~6.2GB VRAM

### Installation

```bash
git clone https://github.com/HeartMuLa/heartlib.git
cd heartlib
uv venv --python 3.10 .venv
source .venv/bin/activate
uv pip install -e .
uv pip install --upgrade datasets transformers
```

**Dependency patches required** (as of Feb 2026):
1. In `src/heartlib/heartmula/modeling_heartmula.py` → `setup_caches` method: add RoPE reinitialization after `reset_caches` try/except
2. In `src/heartlib/pipelines/music_generation.py`: add `ignore_mismatched_sizes=True` to all `HeartCodec.from_pretrained()` calls

### Download Checkpoints

```bash
cd heartlib
hf download --local-dir './ckpt' 'HeartMuLa/HeartMuLaGen'
hf download --local-dir './ckpt/HeartMuLa-oss-3B' 'HeartMuLa/HeartMuLa-oss-3B-happy-new-year'
hf download --local-dir './ckpt/HeartCodec-oss' 'HeartMuLa/HeartCodec-oss-20260123'
```

### Basic Generation

```bash
cd heartlib && source .venv/bin/activate
python ./examples/run_music_generation.py \
  --model_path=./ckpt --version="3B" \
  --lyrics="./assets/lyrics.txt" --tags="./assets/tags.txt" \
  --save_path="./assets/output.mp3" --lazy_load true
```

**Input Formatting:**
- Tags: comma-separated, no spaces — `piano,happy,romantic`
- Lyrics: Use bracketed structural tags — `[Intro]`, `[Verse]`, `[Chorus]`, `[Bridge]`, `[Outro]`

**Key Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `--max_audio_length_ms` | 240000 | Max length in ms (4 min) |
| `--topk` | 50 | Top-k sampling |
| `--temperature` | 1.0 | Sampling temperature |
| `--cfg_scale` | 1.5 | Classifier-free guidance scale |
| `--lazy_load` | false | Load/unload on demand (saves VRAM) |

### Pitfalls
1. **Do NOT use bf16 for HeartCodec** — degrades audio quality. Use fp32 (default).
2. Tags may be ignored by the model; lyrics tend to dominate
3. Triton not available on macOS — Linux/CUDA only for GPU acceleration
4. CPU mode is extremely slow (30-60 min per song vs ~4 min on GPU)

---

## Section 3: Audio Analysis with songsee

Generate spectrograms and multi-panel audio feature visualizations from audio files using the `songsee` CLI tool.

### Prerequisites

Requires Go:
```bash
go install github.com/steipete/songsee/cmd/songsee@latest
```

Optional: `ffmpeg` for formats beyond WAV/MP3.

### Quick Start

```bash
# Basic spectrogram
songsee track.mp3

# Save to specific file
songsee track.mp3 -o spectrogram.png

# Multi-panel visualization grid
songsee track.mp3 --viz spectrogram,mel,chroma,hpss,selfsim,loudness,tempogram,mfcc,flux

# Time slice (start at 12.5s, 8s duration)
songsee track.mp3 --start 12.5 --duration 8 -o slice.jpg
```

### Visualization Types

Use `--viz` with comma-separated values:

| Type | Description |
|------|-------------|
| `spectrogram` | Standard frequency spectrogram |
| `mel` | Mel-scaled spectrogram |
| `chroma` | Pitch class distribution |
| `hpss` | Harmonic/percussive separation |
| `selfsim` | Self-similarity matrix |
| `loudness` | Loudness over time |
| `tempogram` | Tempo estimation |
| `mfcc` | Mel-frequency cepstral coefficients |
| `flux` | Spectral flux (onset detection) |

### Common Flags

| Flag | Description |
|------|-------------|
| `--viz` | Visualization types (comma-separated) |
| `--style` | Color palette: classic, magma, inferno, viridis, gray |
| `--width` / `--height` | Output image dimensions |
| `--start` / `--duration` | Time slice of the audio |
| `-o` | Output file path |

### Notes
- WAV and MP3 are decoded natively; other formats require `ffmpeg`
- Output images can be inspected with `vision_analyze` for automated audio analysis
- Useful for comparing audio outputs, debugging synthesis, or documenting audio processing pipelines
