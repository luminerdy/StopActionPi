# StopActionPi features

Use **Camera** to take photos, **Review Photos** to edit them, and **Finish** to save, narrate, or join movies. Most buttons show their keyboard shortcut. The diagram shows where to find each group of controls. [Menu diagram](MENU.md)

## Choose a movie

| What you see | Key | What it does |
| --- | --- | --- |
| Recent Movies | ↑ / ↓ | Choose a movie you worked on before. You can also click its name. |
| Continue Selected Movie | Enter | Open the selected movie and pick up where you left off. |
| New Movie | N | Name a movie and create its project folder. |
| Open Movie Folder | O | Open a project from another folder, including a newly joined photo folder. |
| Quit / Back to Movie | Esc | Close the welcome screen or return to the movie that is already open. |

The desktop shortcut opens the picker. The app can also open automatically when the desktop starts. The studio opens fullscreen after you choose a movie.

## Controls in an open movie

| Button | Key | What it does |
| --- | --- | --- |
| My Movies | Ctrl+O | Open the movie picker without quitting StopActionPi. |
| Speed | S | Set playback and the next MP4 export to any speed from 2 to 32 frames per second. The app starts at 6 fps. Choose **Use Speed [Enter]** to apply or **Cancel [Esc]** to keep the current speed. Each press of Take Photo saves one photo at every speed. |
| Full Screen / Window View | F11 | Switch between fullscreen and a window. |
| Quit | Q | Close the app. Captured photos are already saved. |

The top of the studio shows the movie name, the number of photos, and the estimated running time.

## Camera

| Button | Key | What it does |
| --- | --- | --- |
| Take Photo | Space | Save one photo from the live camera. |
| Connect Camera | K | Look for the webcam after you plug it in or reconnect it. An existing movie opens in Review Photos when the app starts without a camera. You can still edit and export it. |
| Show Last Photo / Hide Last Photo | O | Show or hide a faint copy of the last photo over the live image so you can see what moved. |
| Replay Last 6 | L | Loop the latest six photos or fewer, at up to 6 fps, to check the motion. |
| Review Photos | ← | Open the latest saved photo. |
| Play Movie | P | Play from the first photo through the newest one. |
| Camera Tools / Hide Camera Tools | C | Show or hide the extra capture tools below. |
| Finish | M | Open the save, narration, and join tools. |

### Camera Tools

| Button | Key | What it does |
| --- | --- | --- |
| Retake Last | R | Retake the most recent photo. A faint copy of the original helps you line up the shot. |
| Take Clean Background | G | Save a reference image of the set before adding a support or character. Keep the camera and lighting in place so **Hide the Support** can use it. |
| Lock Lighting / Lighting Locked | A | On a supported webcam, open a live preview and adjust exposure, gain, and color temperature. **Lock Lighting** keeps those settings and saves them with the movie for the same identifiable camera. **Auto Lighting** goes back to automatic adjustments. **Cancel** restores the previous settings. |

**Lock Lighting** is installed on the current Pi build and verified with the Logitech C270. The feature is pending a GitHub code release and a C920 hardware check.

When retaking a photo, **Show Original Photo / Hide Original Photo [O]** toggles the alignment guide. **Use New Photo [Space]** saves the new shot in the original spot. **Keep Original Photo [Esc]** cancels the retake.

## Review Photos

| Button or control | Key | What it does |
| --- | --- | --- |
| Back to Camera | Esc | Return to the live camera view. Esc closes an open tools panel first. |
| Previous / Next | ← / → | Step through the photos one at a time. |
| Thumbnail strip | Click or scroll | Pick a photo by sight. **Home** and **End** jump to the first and last photo. |
| Play From Here / Pause | Space | Play from the selected photo or pause playback. At the last photo, the button reads **Play Movie**. Press **P** to play the whole movie from the beginning. |
| Edit Photo / Hide Edit Tools | Enter | Show or hide the editing tools for the selected photo. |
| Undo Remove | Ctrl+Z | Bring back the photo you just removed. It stays available in the current session until the next change to the photo sequence. |
| Finish | M | Open the save, narration, and join tools. |

Thumbnail letters show changes attached to a photo. **T** means message, **B** means drawing, **H** means hold, **U** means support cleanup, and **F** means a fade to the next photo.

### Edit Photo

| Button | Key | What it does |
| --- | --- | --- |
| Retake This Photo | R | Replace the selected photo in the same spot. Uses the same alignment guide, **Use New Photo**, and **Keep Original Photo** controls as Retake Last. |
| Move Earlier / Move Later | Shift+← / Shift+→ | Move the selected photo one spot in the sequence. The new order saves immediately. |
| Hold This Photo / Hold | H | Keep the photo on screen for 0.1 to 30 seconds in playback and MP4s. Choose **Save Hold [Enter]** or **Clear Hold**. |
| Duplicate Photo | D | Enter how many extra copies to place after the selected photo, from 1 to 1,000. Each copy can be edited on its own. |
| Add Message / Edit Message | T | Type a message, choose **Top** or **Bottom**, and set how long to **Show for**. Choose **Classic**, **Paper**, **Bright**, or **Sky**, or set **Text Color** and **Background Color** separately. If it looks hard to read, use the suggested **Use Black Text** or **Use White Text**. Choose **Save Message [Ctrl+Enter]** or **Remove Message**. |
| Draw on Photo | B | Pick a color and **Thin**, **Medium**, or **Thick**, then drag to draw. **Undo [Ctrl+Z]** removes the last stroke. **Clear Drawing** clears all strokes in the preview. **Save Drawing [Enter]** keeps the change. |
| Hide the Support | U | Paint over a stand or stick with **Hide Support** to show the clean background in that spot. **Bring Back** restores an area you brushed by mistake. Choose a brush thickness, use **Undo [Ctrl+Z]**, or choose **Clear Cleanup**. **Save Cleanup [Enter]** keeps the change. |
| Fade to Next Photo | F | Blend the selected photo into the next one. Enter up to 30 seconds, or enter **0** to clear the fade. The fade plays while those two photos stay next to each other in that order. |
| Remove Photo | Delete | Open the removal confirmation. Choose **Remove Photo [Enter]** or **Keep Photo [Esc]**. |

Messages, drawings, support cleanups, holds, and fades appear in playback and MP4 exports. If a photo has both a hold and a message, the longer time applies. The editing dialogs offer **Cancel** or **Esc** to keep the last saved version.

## Finish

| Button | Key | What it does |
| --- | --- | --- |
| Save MP4 | E | Export the current movie at the selected speed. The filename starts with the project folder name and includes a date, time, and export label. Earlier exports are kept. |
| Add My Voice | N | Open Recording Studio with the current cut. The studio prepares an MP4 if the current cut or speed changed. |
| Join Movies | J | Put two or more MP4s back to back in the selected order. The new movie keeps the clips’ sound and uses the fastest input frame rate. |
| Join Photo Folders | I | Copy photos into a new folder in the current project. Numbering starts at **000** and continues across folders. Source photos stay in place. Open the new folder through **Open Movie Folder** to work with the combined sequence. |
| Watch Saved Movie | Click | Open the last saved MP4 in the Pi’s default player. |
| Show in Folder | Click | Open the folder containing the last saved MP4. |
| Back | Esc | Return to the view you were using before opening Finish. |

**Watch Saved Movie** and **Show in Folder** appear after a successful MP4 save.

### Recording Studio

Click or drag the timeline to go to a point in the movie. **← / →** move one frame at a time, and **Home / End** go to the start or end. Type a cue in **What will you say?** to keep your line in view.

| Button | Key | What it does |
| --- | --- | --- |
| Choose Existing MP4 | A | Load a saved movie for narration or to revise an earlier recording. |
| Start Here / End Here | 1 / 2 | Mark the section you want to practice or record. |
| Practice | T | Rehearse the marked section with up to three seconds of lead-in. |
| Record This Part / Try Again | R | Record the marked section using a connected microphone. The studio gives you a countdown. Try Again starts a new take. |
| Stop | S | End the current recording or preview. |
| Listen Back | P | Play the marked section with the current take or previously accepted audio so you can hear it with the video. |
| Keep This Take | K | Replace the audio for the part you recorded. The rest of the narration stays in place. |
| Discard This Take | X | Throw away the current take and keep the previously accepted audio. |
| Save Movie | E | Save a new MP4 with the accepted narration and the original video. |
| Close | Esc | Return to StopActionPi. The studio asks before discarding unsaved work. |

### Join Movies and Join Photo Folders

| Button | Key | What it does |
| --- | --- | --- |
| Add Movie / Add Folder | A | Add a movie or folder to the list. You can add folders from more than one project. |
| Move Up / Move Down | U / D | Change the order in which the items will play. |
| Take Off List | Delete | Remove the selected item from the list. The file or folder stays on disk. |
| Join Movies / Join Photo Folders | Enter | Create the combined MP4 or the new numbered photo folder. |
| Close | Esc | Return to StopActionPi. |

When a source folder has a saved photo order, the join uses it. Otherwise, photos sort by filename with numbers in order. The join copies PNG, JPEG, BMP, TIFF, and WebP files in their original formats. Photo edits stay with the source project and appear in MP4s saved from that project.
