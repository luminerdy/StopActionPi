# StopActionPi specification

StopActionPi is a small stop motion studio for a Raspberry Pi 500 and a USB webcam. A child can move a figure, capture a frame with the built-in keyboard, and watch the scene come to life. The app keeps the photos so a movie can be finished or exported later.

## First release

| What a maker needs | Behavior |
| --- | --- |
| See the scene | Show the live camera, photo count, and keyboard guide in one window. Request 1280 × 720 from the Logitech C270. |
| Take a photo | Space saves one clean PNG and updates the thumbnail strip. Holding Space does not add extra photos. |
| Remember what moved | O overlays the newest photo on the live image. The arrow keys let the maker flip between saved photos. |
| See the motion | P plays from the first photo to the latest. L loops the last six at up to six photos per second. Space pauses or resumes review. Esc returns to the camera. |
| Fix a shot | R arms a retake of the last photo. Space saves the replacement to the same slot. Esc cancels and keeps the original. |
| Make a movie | E writes a silent H.264 MP4 at the selected rate. Playback and export default to 12 photos per second. Exports get distinct filenames. |
| Continue tomorrow | Reopen the same project folder and capture continues after the last saved photo. |

## Implementation

- Raspberry Pi OS Desktop on a Pi 500 is the target. A fixed camera mount and steady lighting make changes between photos easier to see.
- OpenCV reads the USB camera. Tk presents the keyboard controls, live view, thumbnails, and review. FFmpeg encodes the MP4.
- A project is an ordinary local folder of numbered PNG files and exported movies. No account or internet connection is required to use the installed studio.
- The repository contains source and instructions. Keep animation projects, photos, exports, credentials, and machine-specific settings outside version control.

## First run acceptance check

1. Launch from the Pi desktop. Confirm the C270 preview appears and the keyboard guide is legible.
2. Capture three distinct photos. Verify the thumbnail strip grows and the saved PNGs contain only the camera image.
3. Move a prop and use O to compare positions. Use the arrows to flip between the last two saved photos.
4. Play all three photos, loop them, and return to live capture.
5. Cancel a retake, then complete one. Check that the photo count stays at three and that only the last shot changes.
6. Save a movie, play the MP4, quit, and reopen the project. The next photo should be numbered four.

## Next experiment

Try an optional second display after the single window workflow is comfortable. Keep the live camera and ghost overlay on the monitor nearest the set. Use the second display for thumbnails and playback while keeping the same keyboard controls.
