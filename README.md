# dictare

Hold a key, talk, release — the text lands in your clipboard and pastes itself.

Local speech-to-text via [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
(`large-v3-turbo`). Nothing leaves the machine. Built for **Romanian dictation
mixed with English technical terms** — the case where generic dictation tools
fall apart — but the language is one config line.

Linux (Wayland/GNOME) and macOS.

## Install

```bash
curl -LsSf https://raw.githubusercontent.com/ProgramatoruLevi/dictare/main/install.sh | bash
```

Detects your OS and installs the matching stack: an isolated Python 3.12 via
[uv](https://github.com/astral-sh/uv), the model (~1.6 GB, once), and the
background services. No system Python is touched. Homebrew is not required on
macOS.

Then **log out and back in** on Linux (group membership), or grant the
permissions macOS asks for (below).

## Use

Hold **Right Ctrl** (Linux) or **Right Command** (macOS), speak, release.

```bash
dictare selftest       # check every component, then test the paste
dictare today          # today's transcripts
dictare history 20     # last 20, with timestamps
dictare last           # the last one
```

Every dictation is saved three ways: clipboard, `history.jsonl`
(one JSON object per line), and `transcripts/YYYY-MM-DD.md`.

## How it works

```
key held ──▶ push-to-talk daemon ──▶ recorder ──▶ WAV
                                                   │
                        model resident in RAM ◀── HTTP POST
                                   │
                    text ──▶ clipboard ──▶ synthetic paste keystroke
```

The model stays loaded in a small local HTTP daemon, so a dictation costs only
inference — no 2-second model load every time. On a 24-core desktop CPU,
22.8 s of audio transcribes in 2.4 s (~9× real time), with no GPU.

Holding the trigger **alone** past 250 ms is what starts a recording. If any
other key goes down mid-gesture the recording is abandoned, so `Ctrl+C` and
friends keep working normally.

## Accuracy on mixed-language speech

Three things do the heavy lifting:

1. **A big model.** `small`/`medium` degrade badly on Romanian.
2. **A forced language.** Auto-detect misfires on short utterances and
   sometimes translates instead of transcribing.
3. **`vocab.txt`** — fed to Whisper as `initial_prompt`. This is where you list
   the jargon it keeps mangling. It is the single highest-leverage file here;
   edit it and `systemctl --user restart dictare`.

## Permissions

**Linux** — `ydotool` writes `/dev/uinput` and the daemon reads `/dev/input`,
both owned by group `input`. The installer adds you; a fresh login applies it.

**macOS** — the OS blocks key reading and key injection until you allow them
explicitly, and **fails silently** when you have not. In System Settings →
Privacy & Security, add whatever launches the agents to **Input Monitoring**
*and* **Accessibility**. Microphone access is prompted on first use.

## Configuration

Linux: `~/.config/systemd/user/dictare.service` ·
macOS: `~/Library/LaunchAgents/com.levi.dictare.plist`

| Variable | Default | Notes |
|---|---|---|
| `DICTARE_LANG` | `ro` | any Whisper language code |
| `DICTARE_MODEL` | `large-v3-turbo` | `large-v3` is better and ~3× slower |
| `DICTARE_BEAM` | `5` | `1` is faster, slightly less accurate |
| `DICTARE_PASTE` | `gui` | `terminal` sends Ctrl+Shift+V (Linux) |
| `DICTARE_KEEP_AUDIO` | `0` | `1` archives the WAVs too |

## Verification status

Honest accounting of what has actually been run:

| | Linux | macOS |
|---|---|---|
| daily real-world use | ✅ | ❌ no Mac available |
| full chain end-to-end | ✅ synthetic key hold | ❌ |
| push-to-talk state machine | ✅ 4/4 | ✅ 5/5 (deterministic clock) |
| Romanian transcription | ✅ 9/10 words, diacritics correct | shared engine |
| syntax / plist validity | ✅ | ✅ |
| `install.sh` run end-to-end | ❌ assembled from verified steps | ❌ |

The macOS port shares the transcription engine and vocabulary with Linux; what
differs is recording, clipboard, paste injection, key reading, and service
management. Its logic is unit-tested, its integration with macOS is not.

## License

MIT
