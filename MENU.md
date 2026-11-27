# StopActionPi menu diagram

Choose a movie, then use **Review Photos [←]** to move from Camera to Review and **Back to Camera [Esc]** to return. An existing movie opens in Review when the camera is disconnected. **Finish [M]** opens from either view. **My Movies [Ctrl+O]** takes you back to the movie picker. [Feature guide](FEATURES.md)

```mermaid
---
config:
  layout: dagre
  markdownAutoWrap: false
  fontFamily: "Arial, sans-serif"
  flowchart:
    nodeSpacing: 20
    rankSpacing: 30
    wrappingWidth: 238
    minNodeWidth: 230
---
flowchart TB
    accTitle: StopActionPi menu map
    accDescr: The movie picker opens the studio. The studio has Camera, Review Photos, and Finish, each with its own tools.

    picker["<b>Choose a movie</b><br/>Recent Movies<br/>Continue Selected Movie [Enter]<br/>New Movie [N] · Open Movie Folder [O]<br/>Quit or Back to Movie [Esc]"]
    studio["<b>Open movie</b><br/>My Movies [Ctrl+O] · Speed [S]<br/>Full Screen or Window View [F11] · Quit [Q]"]
    picker --> studio

    studio --> camera["<b>Camera</b><br/>Take Photo [Space]<br/>Connect Camera [K]<br/>Show or Hide Last Photo [O]<br/>Replay Last 6 [L] · Play Movie [P]"]
    studio --> review["<b>Review Photos [←]</b><br/>Thumbnails · Previous / Next [← / →]<br/>First / last photo [Home / End]<br/>Play From Here or Pause [Space]<br/>Undo Remove [Ctrl+Z]<br/>Back to Camera [Esc]"]
    studio --> finish["<b>Finish [M]</b><br/>Save MP4 [E]<br/>Add My Voice [N]<br/>Join Movies [J] · Join Photo Folders [I]<br/>Watch Saved Movie · Show in Folder<br/>Back [Esc]"]

    camera --> cameraTools["<b>Camera Tools [C]</b><br/>Retake Last [R]<br/>Take Clean Background [G]<br/>Lock Lighting [A]"]
    cameraTools --> cameraDialogs["<b>Retake</b><br/>Show or Hide Original Photo [O]<br/>Use New Photo [Space]<br/>Keep Original Photo [Esc]<br/><br/><b>Camera Lighting</b><br/>Exposure · Gain · Color temperature<br/>Lock Lighting · Auto Lighting · Cancel"]

    review --> photoTools["<b>Edit Photo [Enter]</b><br/>Retake This Photo [R]<br/>Move Earlier / Later [Shift+← / Shift+→]<br/>Hold This Photo [H] · Duplicate Photo [D]<br/>Add or Edit Message [T] · Draw on Photo [B]<br/>Hide the Support [U]<br/>Fade to Next Photo [F] · Remove Photo [Delete]"]
    photoTools --> editDialogs["<b>Photo dialogs</b><br/>Save Hold · Clear Hold<br/>Save Message · Remove Message<br/>Save Drawing · Clear Drawing<br/>Save Cleanup · Clear Cleanup<br/>Remove Photo [Enter] · Keep Photo [Esc]"]

    finish --> finishDialogs["<b>Recording Studio</b><br/>Choose Existing MP4 [A]<br/>Start Here [1] · End Here [2]<br/>Practice [T] · Stop [S]<br/>Record This Part or Try Again [R]<br/>Listen Back [P] · Keep This Take [K]<br/>Discard This Take [X] · Save Movie [E]<br/>Close [Esc]<br/><br/><b>Join Movies or Join Photo Folders</b><br/>Add Movie or Folder [A]<br/>Move Up or Down [U / D]<br/>Take Off List [Delete]<br/>Join [Enter] · Close [Esc]"]
```

**Lock Lighting [A]** appears on the current Pi build. The feature guide describes camera support. [Camera Tools](FEATURES.md#camera-tools)
