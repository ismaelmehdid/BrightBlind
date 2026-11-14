# SecondVision: demo video script (recorded, not the live demo)

Target length: **2:30** (hard cap 3:00). Four scenes, one morning: **fridge, bus, grocery store, the way back.**
Every scene has the same beat, and the edit should make it obvious: **the band hears, the agent decides to look,
the glasses see, the glasses speak.**

Rule for the whole video: everything shown is real system output. Re-take as often as needed, cut the waiting,
but never mock an answer. Where the edit speeds things up, a small "sped up" tag in the corner.

## Cast and crew

| Role | Who | Wears / holds |
|---|---|---|
| Wearer | (pick one) | Vexo band on the left wrist, Ray-Ban Meta glasses, iPhone in the pocket, eyes closed or a sleep mask for wide shots |
| Camera | (pick one) | phone on a gimbal: over-the-shoulder and wide shots |
| Operator | (pick one) | laptop with Recall (`app.py --usb --port COM5 --backend ...`) and the backend dashboard, screen recording on |
| Store staff (scene 3) | a teammate or a friendly employee who agreed | says one line |

## Three video layers, recorded at the same time

1. **World camera**: the gimbal phone. Main picture.
2. **Glasses POV**: the photos and frames the agent looked at (backend dashboard, or the iPhone app's stream
   preview, or `photos/`). Shown picture-in-picture, top right, with a thin green border while the camera is "looking".
3. **Agent screen**: screen recording of the backend dashboard and of Recall at `http://localhost:8100`
   (transcript, decisions, memories). Used for short cut-aways and the captions below.

Audio: record the glasses' speech with a lav mic clipped near the wearer's ear (the glasses speakers are quiet).
Burn in subtitles for **both** voices: wearer in white, agent in yellow.

## Before shooting

- [ ] Recall knows the "usual fridge" (say it out loud near the band the day before, or seed it):
      `POST /api/note {"text": "I always keep milk, eggs, spinach, yogurt and orange juice in the fridge."}`
- [ ] The fridge is set up to match: yogurt, spinach, orange juice in; **milk and eggs missing**.
- [ ] Bus: check the real line and stop you will film. Replace "38" below with that line. Film two buses if
      possible (one wrong, one right).
- [ ] Store: permission to film in the aisle. Dark chocolate on a shelf at chest height, other bars around it.
- [ ] Band: double-tap before connecting, only Recall holds the band, dashboard tab closed.
- [ ] iPhone app connected, Guided Access on, screen awake, mobile data on.
- [ ] Recall page and backend dashboard open on the laptop, screen recording running.

---

## 0. Cold open (0:00 to 0:12)

| Picture | Sound | Caption |
|---|---|---|
| Black. Then a close-up: the wearer's hand finds the band on the wrist by touch. | Soft room tone. | |
| Wide: the wearer in a kitchen, glasses on, eyes closed. | Wearer (V.O.): "I can't see. But I can ask." | **SecondVision** |
| Quick split: band on wrist / glasses on face. | | Band = ears + button. Glasses = eyes + voice. |

## 1. Fridge (0:12 to 0:45)

| Picture | Sound | Caption / what runs |
|---|---|---|
| Over-the-shoulder: wearer opens the fridge. | Wearer: "What am I missing in the fridge?" | `band mic → Deepgram (Pipecat)`; transcript line appears on the agent screen |
| Band LED goes green (if it shows), glasses POV appears: the photo of the open fridge. | (click) | `Planner: needs eyes → one photo` |
| Agent screen: Gemini's item list, then Recall's "usual stock". | | `Vision (Gemini): yogurt, spinach, orange juice` / `Memory (Recall): usually milk, eggs, spinach, yogurt, juice` |
| Close on the wearer's face, nodding. | Glasses: "You have yogurt, spinach and orange juice. You're out of milk and eggs." | |
| Wearer closes the fridge. | Wearer: "Okay. Milk, eggs, and I want dark chocolate." | `Recall stores the shopping list` (memory card appears) |

## 2. Bus stop (0:45 to 1:20)

| Picture | Sound | Caption / what runs |
|---|---|---|
| Door closes, wearer walks to the stop (white cane if they use one). | Wearer: "I'm going to the grocery store." | `Transit (Google Maps): line 38, next bus in 4 min` |
| Glasses speak while walking. | Glasses: "Take the 38 at this stop. It arrives in four minutes. I'll tell you when it's here." | |
| Cut (sped up) to the stop. Text on screen: "3 minutes later". | | `T-60 s: stream on` |
| A wrong bus pulls in. POV PiP: frame with its number. | Glasses: "That's the 22. Not yours, wait." | `Vision: bus number 22 ≠ 38` |
| The right bus pulls in. | Glasses: "This is the 38. Yours. The door is in front of you." | `Vision: 38 ✓ → stream off after boarding` |
| Wearer steps on. | | |

## 3. Grocery store (1:20 to 1:55)

| Picture | Sound | Caption / what runs |
|---|---|---|
| Wearer in the aisle, facing the shelf. | Wearer: "Help me find the dark chocolate." | `Watcher: start burst, goal = dark chocolate bar` |
| | Glasses: "Looking now." | glasses photo burst, 1 per second (green border on PiP) |
| Close-up: the hand moves along the shelf. PiP shows each burst photo. | Glasses: "Higher." … "A bit left." … "That one." | `Guide (Gemini): one direction per photo` |
| Hand closes on the bar. | Wearer: "Got it." | `Watcher: stop burst` |
| Staff member walks by. | Staff: "Fresh bread comes in tomorrow at nine, if you were looking for it." | |
| Close-up: wearer taps the band once. | Wearer: "Thanks!" | `Tap: Recall keeps the last 30 s` (bookmark appears on the Recall page) |

Milk and eggs: one 3-second shot of the wearer putting them in the basket is enough; no need to guide them.

## 4. The way back (1:55 to 2:25)

| Picture | Sound | Caption / what runs |
|---|---|---|
| Short montage, sped up: bus back, glasses POV of the number, door of the building. | Glasses (one line, low in the mix): "This is the 38 home." | same bus scene, no need to show it twice |
| Home. Wearer puts the bag on the table, double-taps the band. | Wearer: "Did I get everything on my list?" | `Double-tap → Planner → Memory (Recall)` |
| Agent screen: Recall's answer built from the morning's memories. | Glasses: "Milk, eggs and dark chocolate. That was all of it." | `Gemini 4 over the whole day's memories` |
| | Wearer: "And what did she say about the bread?" | |
| | Glasses: "Fresh bread comes in tomorrow at nine." | `answer from the bookmarked moment` |
| Wearer smiles, puts the chocolate down. | | |

## 5. Close (2:25 to 2:40)

| Picture | Sound | Caption |
|---|---|---|
| Screen: Recall page at localhost:8100, scrolling the day: what was heard, walk/still timeline, taps, memories. | Wearer (V.O.): "The band listens. The glasses look. The agent decides when." | Pipecat + Deepgram · Gemini 4 · Google Maps · Vexo band · Ray-Ban Meta |
| Card. | | **SecondVision** · Andrii · Ismaël · Tarang · VexoHacks 2026 |

---

## Shot list for the day (in shooting order, not story order)

1. Kitchen: fridge scene (3 to 5 takes), then the "home" end of scene 4 in the same kitchen with the full bag.
2. Street: walk to the stop, both buses, boarding. Then the return bus right after (same stop, other side).
3. Store: aisle guidance (several takes, keep the cleanest "higher / a bit left / that one"), the staff line, the tap.
4. Inserts: hand finding the band, double-tap close-up, single tap close-up, glasses on the face, band LED.
5. Screen recordings: export the matching stretches of the dashboard and the Recall page for each take you keep.

## If something fails on the day

- Bus does not come or the number is hard to read: film at a busier stop, or keep only the "right bus" beat.
  Do not dub an answer the system did not give.
- Guidance is slow: keep the take, cut the gaps between directions, tag it "sped up".
- Glasses speech too quiet: use the lav track; if it is lost, the dashboard shows the exact text that was spoken,
  so the subtitle stays honest.
