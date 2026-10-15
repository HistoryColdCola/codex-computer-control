import AppKit
final class Delegate:NSObject,NSApplicationDelegate,NSTextFieldDelegate {
    var window:NSWindow!;var input:NSTextField!;var result:NSTextField!
    func applicationDidFinishLaunching(_ note:Notification){
        window=NSWindow(contentRect:NSRect(x:200,y:200,width:620,height:320),styleMask:[.titled,.closable],backing:.buffered,defer:false)
        window.title="CCC Local Test - no network";window.center()
        let header=NSTextField(labelWithString:"CCC Local Verification");header.frame=NSRect(x:40,y:240,width:500,height:30)
        input=NSTextField(string:"Ready");input.delegate=self;input.frame=NSRect(x:40,y:175,width:500,height:36)
        let button=NSButton(title:"Verify local draft",target:self,action:#selector(verify));button.frame=NSRect(x:40,y:110,width:250,height:36)
        result=NSTextField(labelWithString:"Waiting for local verification");result.frame=NSRect(x:40,y:40,width:530,height:36)
        for v in [header,input!,button,result!]{window.contentView!.addSubview(v)}
        window.makeKeyAndOrderFront(nil);window.makeFirstResponder(input);NSApp.activate(ignoringOtherApps:true)
        print("READY");fflush(stdout)
    }
    func controlTextDidChange(_ note:Notification){print("DRAFT="+input.stringValue);fflush(stdout)}
    @objc func verify(){result.stringValue=input.stringValue=="本地测试 123🙂" ? "Local verified 123":"Wrong draft";print("VERIFIED="+result.stringValue);fflush(stdout)}
    func applicationShouldTerminateAfterLastWindowClosed(_ sender:NSApplication)->Bool{return true}
}
let app=NSApplication.shared;let delegate=Delegate();app.delegate=delegate;app.setActivationPolicy(.regular);app.run()
