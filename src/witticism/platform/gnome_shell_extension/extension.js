import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const APP_BUS = 'com.stannardlabs.Witticism';
const XML = `<node>
  <interface name="com.stannardlabs.Witticism.Shell">
    <method name="Configure"><arg name="bindings" type="a(ssu)" direction="in"/></method>
    <signal name="Activated"><arg name="id" type="s"/><arg name="timestamp" type="u"/></signal>
    <signal name="Deactivated"><arg name="id" type="s"/><arg name="timestamp" type="u"/></signal>
    <property name="Version" type="u" access="read"/>
    <property name="Ready" type="b" access="read"/>
  </interface>
</node>`;

export default class WitticismExtension extends Extension {
    enable() {
        this.Version = 1;
        this.Ready = true;
        this._bindings = [];
        this._active = new Set();
        this._dbus = Gio.DBusExportedObject.wrapJSObject(XML, this);
        this._dbus.export(Gio.DBus.session, '/com/stannardlabs/Witticism/Shell');
        this._owner = Gio.bus_own_name_on_connection(Gio.DBus.session, 'com.stannardlabs.Witticism.Shell', Gio.BusNameOwnerFlags.NONE, null, null);
        this._eventId = global.stage.connect('captured-event', (_actor, event) => this._onEvent(event));
    }

    disable() {
        for (const id of this._active)
            this._emit('Deactivated', id, 0);
        this._active.clear();
        if (this._eventId)
            global.stage.disconnect(this._eventId);
        this._eventId = 0;
        if (this._owner)
            Gio.bus_unown_name(this._owner);
        this._owner = 0;
        if (this._dbus)
            this._dbus.unexport();
        this._dbus = null;
        this.Ready = false;
    }

    ConfigureAsync([bindings], invocation) {
        if (!this._isWitticism(invocation.get_sender())) {
            invocation.return_dbus_error('com.stannardlabs.Witticism.Error.AccessDenied', 'Caller is not Witticism');
            return;
        }
        this._bindings = bindings.map(([id, accelerator, trigger]) => ({id, ...this._parse(accelerator), hold: trigger === 1}));
        invocation.return_value(new GLib.Variant('()', []));
    }

    _isWitticism(sender) {
        try {
            const reply = Gio.DBus.session.call_sync(
                'org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'GetNameOwner',
                new GLib.Variant('(s)', [APP_BUS]), new GLib.VariantType('(s)'), Gio.DBusCallFlags.NONE, 1000, null
            );
            return reply.deepUnpack()[0] === sender;
        } catch (_error) {
            return false;
        }
    }

    _parse(accelerator) {
        const parts = accelerator.split('+').map(part => part.trim()).filter(Boolean);
        const key = parts.pop().toLowerCase();
        return {key, modifiers: new Set(parts.map(part => part.toLowerCase()))};
    }

    _keyName(symbol) {
        for (let i = 1; i <= 12; i++) {
            if (symbol === Clutter[`KEY_F${i}`])
                return `f${i}`;
        }
        const special = new Map([
            [Clutter.KEY_space, 'space'], [Clutter.KEY_Tab, 'tab'],
            [Clutter.KEY_Return, 'enter'], [Clutter.KEY_Escape, 'esc'],
        ]);
        if (special.has(symbol))
            return special.get(symbol);
        const unicode = Clutter.keysym_to_unicode(symbol);
        return unicode ? String.fromCodePoint(unicode).toLowerCase() : '';
    }

    _modifiersMatch(required, state) {
        const checks = new Map([
            ['ctrl', Clutter.ModifierType.CONTROL_MASK], ['control', Clutter.ModifierType.CONTROL_MASK],
            ['alt', Clutter.ModifierType.MOD1_MASK], ['shift', Clutter.ModifierType.SHIFT_MASK],
            ['super', Clutter.ModifierType.SUPER_MASK], ['meta', Clutter.ModifierType.META_MASK],
        ]);
        for (const modifier of required) {
            if (!checks.has(modifier) || !(state & checks.get(modifier)))
                return false;
        }
        return true;
    }

    _onEvent(event) {
        if (Main.sessionMode.isLocked)
            return Clutter.EVENT_PROPAGATE;
        const type = event.type();
        if (type !== Clutter.EventType.KEY_PRESS && type !== Clutter.EventType.KEY_RELEASE)
            return Clutter.EVENT_PROPAGATE;
        const key = this._keyName(event.get_key_symbol());
        const state = event.get_state();
        const timestamp = event.get_time();
        for (const binding of this._bindings) {
            if (binding.key !== key)
                continue;
            if (type === Clutter.EventType.KEY_RELEASE && this._active.has(binding.id)) {
                this._active.delete(binding.id);
                if (binding.hold)
                    this._emit('Deactivated', binding.id, timestamp);
                continue;
            }
            if (!this._modifiersMatch(binding.modifiers, state))
                continue;
            if (type === Clutter.EventType.KEY_PRESS && !this._active.has(binding.id)) {
                this._active.add(binding.id);
                this._emit('Activated', binding.id, timestamp);
            }
        }
        return Clutter.EVENT_PROPAGATE;
    }

    _emit(signal, id, timestamp) {
        this._dbus?.emit_signal(signal, new GLib.Variant('(su)', [id, timestamp]));
    }
}
