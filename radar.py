import sys, time, math, warnings, collections
import matplotlib
matplotlib.use('TkAgg') #use tkinter early to fix window issues
import matplotlib.pyplot as plt
import numpy as np
import serial, serial.tools.list_ports
from matplotlib.collections import LineCollection #efficient line manipulation 
from matplotlib.widgets import Button, Slider     # <-- UI controls (button + sliders)

#Serial port selection
COMMON_VID_PID = {(0x2341,0x0043),(0x2341,0x0001),(0x2341,0x0243), #compare ports found with common vendor and product ids
                  (0x2A03,0x0043),(0x2A03,0x0001),
                  (0x1A86,0x7523),(0x1A86,0x5523),
                  (0x10C4,0xEA60),(0x0403,0x6001)}
KEYWORDS = ("arduino","ch340","cp210","ftdi","usb-serial","usb serial") #compare ports with text name
#port choosing logic
def choose_port(cli_hint=None):
    ports = list(serial.tools.list_ports.comports())
    if not ports: raise IOError("No serial ports found.")
    print("Detected ports:")
    for i,p in enumerate(ports):
        print(f"  [{i}] {p.device} | desc='{p.description}' | mfg='{p.manufacturer}' "
              f"| hwid='{p.hwid}' | vid={p.vid} pid={p.pid}")
    if cli_hint:
        for p in ports:
            if p.device.lower()==cli_hint.lower(): return p.device
    for p in ports:
        if p.vid is not None and p.pid is not None and (p.vid,p.pid) in COMMON_VID_PID:
            return p.device
    for p in ports:
        txt = f"{p.description} {p.manufacturer}".lower()
        if any(k in txt for k in KEYWORDS): return p.device
    if len(ports)==1:
        warnings.warn("No clear match; using the only port found.")
        return ports[0].device
    warnings.warn("Multiple ports; defaulting to the first.")
    return ports[0].device

cli_port = sys.argv[1] if len(sys.argv)>1 else None
port_name = choose_port(cli_port) #allow cli port specification

BAUD = 115200   # must match Arduino sketch 
print(f"\nOpening {port_name} @ {BAUD} baud...")
ser = serial.Serial(port=port_name, baudrate=BAUD, timeout=0)  # non-blocking timeout to prevent windows tk errors
time.sleep(2.0)
ser.reset_input_buffer() #allow board to wakeup and clear tx 

#Plot window
WIN_W, WIN_H = 1280, 720 #default window size
WIN_X, WIN_Y = 120, 80

plt.ion() #allow borders to be full screened if initially windowed
fig = plt.figure("Arduino Radar Scanner", figsize=(WIN_W/96, WIN_H/96), dpi=96, facecolor='black') #background
try:
    fig.canvas.manager.window.wm_geometry(f"{WIN_W}x{WIN_H}+{WIN_X}+{WIN_Y}")
except Exception:
    pass

ax = fig.add_subplot(111, polar=True, facecolor='#288526') #semi circle and grid
ax.set_position([0.06, 0.08, 0.70, 0.84])  # <-- make room for the control panel on the right
ax.set_theta_direction(-1)     # clockwise
ax.set_theta_offset(np.pi)     # 0° at left
ax.set_xlim([0.0, np.pi])      # 0..180°
ax.set_ylim([0.0, 100.0])      # cm
ax.set_thetagrids(np.linspace(0.0, 180.0, 7))
ax.tick_params(axis='both', colors='w')
ax.grid(True, which='major', color='#75d950', linestyle='-', alpha=0.5)

# Sweep line (live)
sweep_line_plot, = ax.plot([], color='#79f07b', linewidth=3.0, alpha=0.85) #current sweep line

#Full-length fading trails
# Each "hit" is a segment from r=0 to r=distance at a fixed theta.
TRAIL_MAX_SECONDS = 5       # total visible duration
HALF_LIFE = 1               # seconds; exponential fade 50%/half-life
ALPHA_MIN = 0.03            # below this alpha, drop the segment
MAX_HITS = 4000             # cap to keep memory bounded
HIT_RGB = (0.49, 1.00, 0.49)   # green-ish echo lines (alpha varies)

# store (theta_rad, distance_cm, t_created, seq)
hits = collections.deque(maxlen=MAX_HITS) #store hits fast
_hit_seq = 0  # monotonically increasing sequence number for spacing labels

# Use a LineCollection so we can redraw many segments efficiently
trail = LineCollection([], linewidths=2.2, antialiased=True)
trail.set_transform(ax.transData)  # polar data coords
ax.add_collection(trail)

plt.show(block=False)
plt.pause(0.05)

#UI controls: toggle labels, font size slider, spacing slider
# keep your comments; new ones below explain the UI widgets only.
# Button to toggle showing text at the end of the line (distance)
ui_ax_toggle = fig.add_axes([0.80, 0.83, 0.17, 0.07])  # x, y, w, h
btn_toggle = Button(ui_ax_toggle, 'Toggle Length Text')

# Slider for text size
ui_ax_font = fig.add_axes([0.80, 0.72, 0.17, 0.03])
sld_font = Slider(ui_ax_font, 'Text Size', 6, 24, valinit=10, valstep=1)

# Slider for spacing between labeled readings (every Nth trail)
ui_ax_spacing = fig.add_axes([0.80, 0.64, 0.17, 0.03])
sld_spacing = Slider(ui_ax_spacing, 'Label Every N', 1, 10, valinit=1, valstep=1)

#  make slider labels visible on dark bg
for a in (ui_ax_font, ui_ax_spacing):
    a.set_facecolor('#1b1b1b')             # darker panel behind slider
for s in (sld_font, sld_spacing):
    s.label.set_color('white')             # left-side label (e.g., "Text Size")
    s.valtext.set_color('white')           # numeric value on the right

# Runtime state controlled by UI
show_labels = False
label_fontsize = int(sld_font.val)
label_every = int(sld_spacing.val)

# For managing label artists (Text instances)
_label_artists = []

def _clear_labels():
    # remove existing text artists from the axes
    global _label_artists
    for t in _label_artists:
        try:
            t.remove()
        except Exception:
            pass
    _label_artists = []

def _on_toggle(event):
    # flip the visibility flag and clear any existing labels when hiding
    global show_labels
    show_labels = not show_labels
    if not show_labels:
        _clear_labels()

def _on_font_change(val):
    # update target font size; labels will refresh on next frame
    global label_fontsize
    label_fontsize = int(val)

def _on_spacing_change(val):
    # update modulo spacing; ensure at least 1
    global label_every
    label_every = max(1, int(val))

btn_toggle.on_clicked(_on_toggle)
sld_font.on_changed(_on_font_change)
sld_spacing.on_changed(_on_spacing_change)

#Non-blocking serial line parser
buf = ""
def parse(s: str):
    s = s.strip()
    if not s or ',' not in s: return None
    a_str, d_str = s.split(',', 1)
    try: ang = int(float(a_str))
    except ValueError: return None
    if not (0 <= ang <= 180): return None
    if d_str.upper() == "NA":
        return ang, np.nan
    try:
        dist = float(d_str)
    except ValueError:
        return None
    if not (0.0 <= dist <= 100.0):
        dist = np.nan
    return ang, dist

#Helper to rebuild segments with fading
def rebuild_trails(now):
    segs = []
    cols = []
    # Exponential fade feels smoother than linear
    for th, r, t0, _seq in list(hits):
        age = now - t0
        if age > TRAIL_MAX_SECONDS:
            continue
        # alpha = 0.5 ** (age / HALF_LIFE)  # exponential
        alpha = math.exp(-age / HALF_LIFE)
        if alpha < ALPHA_MIN:
            continue
        segs.append([(th, 0.0), (th, r)])       # full radial line
        cols.append((*HIT_RGB, alpha))
    trail.set_segments(segs)
    if cols:
        trail.set_colors(cols)
    else:
        trail.set_colors([(*HIT_RGB, 0.0)])

def rebuild_labels(now):
    # draw text at the end of selected trails (every Nth), with fading alpha matching the line
    _clear_labels()
    if not show_labels:
        return
    # Iterate newest-to-oldest so the freshest labels appear on top
    for th, r, t0, seq in reversed(hits):
        age = now - t0
        if age > TRAIL_MAX_SECONDS:
            continue
        alpha = math.exp(-age / HALF_LIFE)
        if alpha < ALPHA_MIN:
            continue
        # spacing: only label every Nth reading by sequence number
        if (seq % label_every) != 0:
            continue
        # Create text at the line end
        txt = f"{r:.0f} cm"
        t = ax.text(th, r, txt,
                    fontsize=label_fontsize,
                    color=(HIT_RGB[0], HIT_RGB[1], HIT_RGB[2], alpha),
                    ha='left', va='center', transform=ax.transData)
        _label_artists.append(t)

print("Reading from serial... (close the Arduino Serial Monitor)")

#Main loop
last_gui = time.perf_counter()
while True:
    # Read all available bytes without blocking
    """
    Reads whatever bytes are available right now; never waits.

    Splits on newlines safely (keeps partial tail in buf).

    For each complete reading:

    converts angle -> radians,

    moves the sweep line to that angle immediately,

    if distance is valid, records a hit with a timestamp (for fading).
    """
    n = ser.in_waiting
    if n:
        chunk = ser.read(n).decode("utf-8", errors="replace")
        buf += chunk
        if '\n' in buf:
            lines = buf.splitlines(keepends=False)
            if not buf.endswith('\n'):
                buf = lines[-1]; lines = lines[:-1]
            else:
                buf = ""
            for line in lines:
                parsed = parse(line)
                if not parsed:
                    continue
                ang, dist = parsed
                rad = math.radians(ang)
                # Move live sweep
                sweep_line_plot.set_data([rad, rad], [0.0, 100.0])
                # Add a full-length trail segment if distance is valid
                if not np.isnan(dist):
                    _hit_seq += 1
                    hits.append((rad, float(dist), time.perf_counter(), _hit_seq))

    # Refresh GUI ~100 fps max
    now = time.perf_counter()
    if now - last_gui >= 0.01:
        rebuild_trails(now)
        rebuild_labels(now)          # <-- update labels after rebuilding trails
        fig.canvas.draw_idle()
        plt.pause(0.001) #give tk some time to execute gui
        last_gui = now
