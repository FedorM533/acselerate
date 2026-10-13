// Расширение GNOME Shell для «Фокус-пруда».
//
// На Wayland обычная программа не может узнать, какое окно активно, — это знает
// только сама GNOME Shell. Расширение отвечает на три вопроса по D-Bus (только
// для этого компьютера, шина сеанса пользователя):
//   Active()      — pid и заголовок окна в фокусе (JSON);
//   Windows()     — pid и заголовки всех обычных окон (для белого списка);
//   Close(pid)    — вежливо закрыть окна процесса (как кнопка «×»).
// Строки отдаём только из ASCII (\uXXXX), чтобы их было просто разобрать в Python.

import Gio from 'gi://Gio';
import Meta from 'gi://Meta';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const BUS_NAME = 'org.carpo.FocusWindow';
const OBJECT_PATH = '/org/carpo/FocusWindow';
const IFACE = `<node>
  <interface name="org.carpo.FocusWindow">
    <method name="Active"><arg type="s" direction="out" name="json"/></method>
    <method name="Windows"><arg type="s" direction="out" name="json"/></method>
    <method name="Close">
      <arg type="u" direction="in" name="pid"/>
      <arg type="b" direction="out" name="sent"/>
    </method>
  </interface>
</node>`;

function asciiJson(value) {
    return JSON.stringify(value).replace(/[\u007f-￿]/g,
        c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
}

function describe(win) {
    return {pid: win.get_pid(), title: win.get_title() || '', wm_class: win.get_wm_class() || ''};
}

function normalWindows() {
    return global.display.list_all_windows()
        .filter(w => w.get_window_type() === Meta.WindowType.NORMAL && !w.is_skip_taskbar());
}

class FocusWindowService {
    Active() {
        const win = global.display.focus_window;
        return asciiJson(win ? describe(win) : {});
    }

    Windows() {
        return asciiJson(normalWindows().map(describe));
    }

    Close(pid) {
        const wins = normalWindows().filter(w => w.get_pid() === pid);
        const time = global.get_current_time();
        wins.forEach(w => w.delete(time));
        return wins.length > 0;
    }
}

export default class CarpoFocusExtension extends Extension {
    enable() {
        this._dbus = Gio.DBusExportedObject.wrapJSObject(IFACE, new FocusWindowService());
        this._dbus.export(Gio.DBus.session, OBJECT_PATH);
        this._ownerId = Gio.bus_own_name_on_connection(
            Gio.DBus.session, BUS_NAME, Gio.BusNameOwnerFlags.NONE, null, null);
    }

    disable() {
        if (this._ownerId) {
            Gio.bus_unown_name(this._ownerId);
            this._ownerId = 0;
        }
        if (this._dbus) {
            this._dbus.unexport();
            this._dbus = null;
        }
    }
}
