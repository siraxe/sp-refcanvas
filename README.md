# RefCanvas

A reference-image dock panel for Adobe Substance 3D Painter. Drop or load
images onto a collapsible canvas, arrange them as transformable collage
layers, pick colours from the reference and push them straight into the
active paint tool's Base Color with `LIVE ON`. Pure Python, using the
Qt6/PySide6 binding on Painter 10.1 and newer and Qt5/PySide2 on earlier
builds. Swatches, colours, layout and the collage persist between
sessions.

## Hotkeys

<table>
  <tr>
    <th width="30%">Hotkey</th>
    <th width="70%">Video</th>
  </tr>
  <tr>
    <td><b>Color Swap</b> &mdash; <code>Shift + X</code><br>(rebindable)</td>
    <td rowspan="6">
      <video src="git/example.mp4" width="100%" controls muted>
        <a href="git/example.mp4">watch the demo video</a>
      </video>
    </td>
  </tr>
  <tr>
    <td><b>Transform Layer</b> &mdash; <code>Ctrl + T</code><br>(rebindable)</td>
  </tr>
  <tr>
    <td><b>Add Swatch</b> &mdash; <code>Alt + C</code><br>(rebindable)</td>
  </tr>
  <tr>
    <td><b>Fit Layers</b> &mdash; <code>Alt + F</code><br>(inside panel)</td>
  </tr>
  <tr>
    <td><b>Toggle LIVE ON</b> &mdash; <code>Alt + Z</code><br>(inside panel)</td>
  </tr>
  <tr>
    <td><b>Delete Layer</b> &mdash; <code>Delete</code><br>(panel focus)</td>
  </tr>
</table>

Rebindable shortcuts can be changed in `REFCANVAS Settings`, where all
hotkeys can also be switched off at once.

## License

Released under the [MIT License](LICENSE).
