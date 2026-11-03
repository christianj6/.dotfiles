# prescient UI: show bro's LISTENING tier (cross-repo ask from bro)

bro landed listening mode (`52f5a08`, not pushed). The core enters `tier = "LISTENING"` while it holds the owner's thoughts without answering. prescient's life view maps only `STANDBY` and `MUTED`, so **LISTENING renders as "on"** — the owner would see a normal listening mic while bro is silently accumulating thoughts and answering nothing. That is the worst possible state to be wrong about: the owner talks, gets no reply, and the UI says everything is fine.

Nothing is broken today — the live core predates the tier — so this must land **before** the core is restarted.

## Two sites, both in `prescient/gantt/static/index.html`

### 1. `listenRowsHtml` — line ~4940
```js
const word = v.tier === 'STANDBY' ? 'standby' : v.tier === 'MUTED' ? 'muted' : 'on';
```
Add LISTENING. Note the second half of that function derives the *toggle* button's action from `word`:

```js
const tier = word === 'on' ? ['standby', 'rest', ...]
  : word === 'muted' ? ['unmute', ...] : ['wake', 'wake', 'bro listens to everything again'];
```
`LISTENING` must **not** fall into the `else` branch's `wake` (it is not asleep, and there is nothing to wake). And its own toggle should not be "standby" either — the honest exit from listening is whatever bro already accepts. Choose deliberately:
- `word === 'listening'` → toggle sends `stop` for the tier if bro supports it, else `standby`; label it plainly ("listening · pause"). **Confirm which action bro's `/api/voice` accepts before wiring it** — do not invent an action name that bro will 400. If bro has no listening-exit action, the row should be *informational only* (a disabled row saying bro is holding your thoughts, closed by "I'm done" or a mute), which is truthful and needs no new endpoint.

### 2. `broVoiceTag` — line ~4994
```js
const word = v.session === 'selfplay' ? 'self-play' : !v.running ? 'off'
  : v.tier === 'STANDBY' ? 'standby' : v.tier === 'MUTED' ? 'muted' : '';
```
Add `: v.tier === 'LISTENING' ? 'listening' : `. The tray tag is the one that matters most — it is the always-visible signal.

Also give `.lw-tray-voice.listening` a colour in the CSS block at ~1027 (currently only `.muted` and `.off`/`.self-play` are styled). It should read as *active but different from ordinary listening* — suggest a distinct accent rather than grey (grey reads "off", the opposite of the truth).

### 3. `voiceAct` optimistic state — line ~4945
```js
state.voice = { ...v, tier: action === 'standby' ? 'STANDBY' : action === 'mute' ? 'MUTED' : 'ACTIVE', since_ms: 0 };
```
If a listening-exit action is wired, this map needs it too, or the tag will flip to ACTIVE and then correct itself 2 s later on the next poll. Only if you add an action.

## Verification

The page has its own self-test block (`checks.broVoiceTag`, ~14172). Extend it — do not hand-verify only:

1. `broVoiceTag({running: true, tier: 'LISTENING', since_ms: 60000}, 0, 0)` matches `class="lw-tray-voice listening"` and the tooltip says bro is holding your thoughts, not "bro's voice: listening for 1 min" (the plain phrasing would imply it is answering).
2. `broVoiceTag({running: true, tier: 'ACTIVE'}, 0, 0) === ''` still holds (unchanged behaviour for the normal case).
3. `listenRowsHtml({running: true, tier: 'LISTENING'})` shows a listening state whose toggle is the action you verified bro accepts — or a disabled/informational row. Assert the *absence* of `wake` for this tier.
4. The existing STANDBY/MUTED/off/self-play assertions all still pass.
5. Smoke: load the page, and with a stubbed `/api/voice` returning `tier: 'LISTENING'`, confirm the tray shows "listening" rather than nothing.

## Do not

- Do not map LISTENING to "on" as a fallback for an unknown tier. An unknown tier should render as the *conservative* thing (visibly not answering), not the normal one — a future tier added by bro should show up as "unknown", not silently as healthy.
