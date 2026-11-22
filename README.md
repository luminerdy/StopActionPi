# StopActionPi

Make a stop motion movie with a Raspberry Pi 500, a Logitech C270 USB webcam, and the built-in keyboard. Move a figure a little, take a photo, and play your movie as it grows. The live camera, recent photos, and key guide fit in one window. See the [project specification](SPEC.md) for the design and first run acceptance check.

## Install on the Pi

Connect the webcam to USB. From a terminal on the Pi desktop, run:

```bash
sudo apt update
sudo apt install python3-opencv python3-tk ffmpeg v4l-utils
git clone https://github.com/luminerdy/StopActionPi.git
cd StopActionPi
python3 stop_motion.py --project projects/first_movie
```

Use the system Python with these OS packages. The program needs a graphical desktop; an ordinary SSH terminal cannot display its preview.

## Make a movie

Fix the camera in place, light the scene, and press **Space** for the first photo. Move your subject a little and press **Space** again. The newest photos appear below the live view as you go. If another window has keyboard focus, use **Alt+Tab** to return to Stop Motion Studio.

| Key | What it does |
| --- | --- |
| **Space** | Take and save a photo in the live view. Pause or play in review. |
| **O** | Toggle a faint overlay of the last photo so you can see what moved. |
| **← / →** | Open the latest saved photo, then step through the photos one by one. |
| **P** | Play the movie from the first photo through the newest one. |
| **L** | Loop up to six recent photos slowly to check the motion. |
| **Esc** | Return to the live camera or cancel a retake. |
| **R** | Set up a retake. **Space** replaces the last photo and **Esc** keeps it. |
| **E** | Save an MP4 in the project folder. Wait for “Movie saved!” on screen. |
| **Q** | Quit. Your photos are already saved. |

The default is 12 photos per second of finished video: 120 photos make 10 seconds. Try small, consistent movements. Keep your hands out of the scene before capturing; wait briefly after touching the camera or table.

## Resume or change playback speed

Run the same project command to resume. Use a different project folder for each movie. Do not open the same project in multiple program instances.

```bash
python3 stop_motion.py --project projects/first_movie --fps 8
python3 stop_motion.py --project projects/first_movie --fps 12 --export-only
```

Export-only works without a webcam or preview. Each export gets a new filename. Original PNG photos remain in the project folder; avoid renaming or deleting individual frames because export expects consecutive numbering from 1. Movies are silent.

## Camera troubleshooting

Close other programs using the camera. List devices with:

```bash
v4l2-ctl --list-devices
```

If necessary, try `--camera 1` or another device number. The program requests 1280 by 720; the webcam driver chooses the actual supported resolution. All frames within a project must have the same dimensions.

For flicker, use steady lighting and avoid changing daylight. Inspect available exposure and white-balance controls with `v4l2-ctl -d /dev/video0 --list-ctrls-menus`. Supported controls vary; locking exposure and white balance can improve consistency.

## Hardware verification

On a new setup, capture three frames, export, and play the MP4 on the Pi before starting a long movie. See the [acceptance check](SPEC.md#first-run-acceptance-check) for the complete walkthrough.

References: [Logitech C270 specifications](https://support.logi.com/hc/en-001/articles/360023393913-Logitech-HD-Webcam-C270-Technical-Specifications) and [Raspberry Pi camera documentation, including USB webcams](https://www.raspberrypi.com/documentation/accessories/camera-software.html).
