const Desklet = imports.ui.desklet;
const St = imports.gi.St;
const Mainloop = imports.mainloop;
const GLib = imports.gi.GLib;

function MyDesklet(metadata, desklet_id) {
    this._init(metadata, desklet_id);
}

MyDesklet.prototype = {
    __proto__: Desklet.Desklet.prototype,

    _init: function(metadata, desklet_id) {
        Desklet.Desklet.prototype._init.call(this, metadata, desklet_id);
        
        this.setupUI();
        this.update();
    },

    setupUI: function() {
        // Main container
        this.window = new St.Bin();
        this.window.style_class = "my-desklet-container";
        
        // Content
        this.content = new St.Label();
        this.content.set_text("Hello, Linux Mint!");
        this.content.style_class = "my-desklet-content";
        
        this.window.set_child(this.content);
        this.setContent(this.window);
    },

    update: function() {
        // Update logic here
        // This function can be called periodically to update the desklet
        
        // Schedule next update (every 60 seconds)
        this.timeout = Mainloop.timeout_add_seconds(60, () => {
            this.update();
            return false;
        });
    },

    on_desklet_removed: function() {
        if (this.timeout) {
            Mainloop.source_remove(this.timeout);
        }
    }
};

function main(metadata, desklet_id) {
    return new MyDesklet(metadata, desklet_id);
}

