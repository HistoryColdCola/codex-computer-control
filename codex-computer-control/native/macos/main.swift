import Foundation
import AppKit
import ApplicationServices
import Vision
import Darwin
#if compiler(>=5.9)
import ScreenCaptureKit
#endif

private typealias DisplayCapture = @convention(c) (UInt32) -> Unmanaged<CGImage>?
private let legacyCapture:DisplayCapture? = {
    guard let symbol=dlsym(UnsafeMutableRawPointer(bitPattern:-2),"CGDisplayCreateImage")else{return nil}
    return unsafeBitCast(symbol,to:DisplayCapture.self)
}()
var lastCaptureBackend="none"
#if compiler(>=5.9)
final class CaptureBox: @unchecked Sendable {
    let lock=NSLock()
    var result:Result<CGImage,Error>?
    func finish(_ value:Result<CGImage,Error>){lock.lock();result=value;lock.unlock()}
    func read()->Result<CGImage,Error>?{lock.lock();defer{lock.unlock()};return result}
}
#endif
func modernCapture()throws->CGImage? {
#if compiler(>=5.9)
    if #available(macOS 14.0,*) {
        let box=CaptureBox()
        SCShareableContent.getExcludingDesktopWindows(false,onScreenWindowsOnly:true){content,error in
            if let error=error{box.finish(.failure(error));return}
            guard let display=content?.displays.first(where:{$0.displayID==CGMainDisplayID()})else{box.finish(.failure(Failure("Primary display unavailable")));return}
            let filter=SCContentFilter(display:display,excludingWindows:[])
            let config=SCStreamConfiguration();config.width=display.width;config.height=display.height;config.showsCursor=false
            SCScreenshotManager.captureImage(contentFilter:filter,configuration:config){image,error in
                if let image=image{box.finish(.success(image))}else{box.finish(.failure(error ?? Failure("ScreenCaptureKit capture failed")))}
            }
        }
        let end=Date(timeIntervalSinceNow:2)
        while box.read()==nil {try check();if Date()>end{throw Failure("ScreenCaptureKit capture timeout")};RunLoop.current.run(until:Date(timeIntervalSinceNow:0.005))}
        return try box.read()!.get()
    }
#endif
    return nil
}

struct Failure: Error, CustomStringConvertible { let description: String; init(_ s:String){description=s} }
let dataDir = ProcessInfo.processInfo.environment["CCC_DATA_DIR"] ?? NSHomeDirectory()+"/.local/share/codex-computer-control"
let stopFile = dataDir+"/STOP"
let parent = getppid()
func front() -> NSRunningApplication? {
    RunLoop.current.run(until:Date(timeIntervalSinceNow:0.001))
    return NSWorkspace.shared.frontmostApplication
}
func appID()->String { return front().map { String($0.processIdentifier) } ?? "" }
func screenSize()->CGSize { let b=CGDisplayBounds(CGMainDisplayID());return b.size }
func available()->Bool {
    let d=CGMainDisplayID()
    let session=CGSessionCopyCurrentDictionary() as? [String:Any] ?? [:]
    return CGDisplayIsActive(d) != 0 && CGDisplayIsAsleep(d) == 0 && !(session["CGSSessionScreenIsLocked"] as? Bool ?? false)
}
func check(_ expected:String?=nil, input:Bool=false)throws {
    if getppid() != parent { throw Failure("Controller disconnected") }
    if FileManager.default.fileExists(atPath:stopFile){throw Failure("Emergency stop active")}
    if !available(){throw Failure("Desktop locked, inactive or asleep")}
    if let expected=expected, !expected.isEmpty,appID() != expected {throw Failure("Foreground app changed; do not replay input")}
    if input {
        if !AXIsProcessTrusted(){throw Failure("Enable Accessibility for the hosting process")}
        let p=NSEvent.mouseLocation;let h=screenSize().height
        if p.x<=0 && h-p.y<=0 {throw Failure("Pointer at emergency stop corner")}
    }
}
func position()->CGPoint { return CGEvent(source:nil)?.location ?? .zero }
func point(_ x:Int,_ y:Int)throws->CGPoint {
    let s=screenSize();if x<0 || y<0 || x>=Int(s.width) || y>=Int(s.height) || (x==0&&y==0){throw Failure("Point outside primary display or stop corner")}
    return CGPoint(x:x,y:y)
}
func rect(_ value:Any?)throws->CGRect? {
    guard let r=value as? [String:Any] else{return nil}
    guard let x=r["x"] as? Int,let y=r["y"] as? Int,let w=r["width"] as? Int,let h=r["height"] as? Int else {throw Failure("Invalid region")}
    let s=screenSize();if x<0||y<0||w<=0||h<=0||x+w>Int(s.width)||y+h>Int(s.height){throw Failure("Region outside primary display")}
    return CGRect(x:x,y:y,width:w,height:h)
}
func sleepGuard(_ seconds:Double,_ expected:String?)throws {
    let end=Date(timeIntervalSinceNow:seconds)
    repeat{try check(expected,input:true);Thread.sleep(forTimeInterval:min(0.02,max(0,end.timeIntervalSinceNow)))}while end.timeIntervalSinceNow>0
}
let keyCodes:[String:CGKeyCode] = ["a":0,"s":1,"d":2,"f":3,"h":4,"g":5,"z":6,"x":7,"c":8,"v":9,"b":11,"q":12,"w":13,"e":14,"r":15,"y":16,"t":17,"1":18,"2":19,"3":20,"4":21,"6":22,"5":23,"9":25,"7":26,"8":28,"0":29,"o":31,"u":32,"i":34,"p":35,"enter":36,"return":36,"l":37,"j":38,"k":40,"n":45,"m":46,"tab":48,"space":49,"backspace":51,"esc":53,"escape":53,"command":55,"cmd":55,"meta":55,"shift":56,"alt":58,"option":58,"ctrl":59,"control":59,"f1":122,"f2":120,"f3":99,"f4":118,"f5":96,"f6":97,"f7":98,"f8":100,"f9":101,"f10":109,"f11":103,"f12":111,"home":115,"pageup":116,"delete":117,"end":119,"pagedown":121,"left":123,"right":124,"down":125,"up":126]
func modifier(_ code:CGKeyCode)->CGEventFlags {
    switch code{case 55:return .maskCommand;case 56:return .maskShift;case 58:return .maskAlternate;case 59:return .maskControl;default:return []}
}
func keyEvent(_ code:CGKeyCode,_ down:Bool,_ pid:pid_t,_ flags:CGEventFlags=[],_ text:[UniChar]?=nil)throws {
    guard let e=CGEvent(keyboardEventSource:nil,virtualKey:code,keyDown:down)else{throw Failure("Unable to create keyboard event")}
    e.flags=flags
    if let text=text {text.withUnsafeBufferPointer{p in e.keyboardSetUnicodeString(stringLength:text.count,unicodeString:p.baseAddress)}}
    e.postToPid(pid)
}
func mouseEvent(_ kind:CGEventType,_ p:CGPoint,_ button:CGMouseButton,_ pid:pid_t,_ count:Int=1)throws {
    guard let e=CGEvent(mouseEventSource:nil,mouseType:kind,mouseCursorPosition:p,mouseButton:button)else{throw Failure("Unable to create mouse event")}
    e.setIntegerValueField(.mouseEventClickState,value:Int64(count));e.post(tap:.cgSessionEventTap)
}
func action(_ a:[String:Any],_ expected:String?)throws->[String:Any] {
    try check(expected,input:true)
    guard let pid=front()?.processIdentifier else{throw Failure("No foreground application")}
    let kind=a["action"] as? String ?? ""
    if ["invoke","set_value","focus_element"].contains(kind){return try elementAction(a,expected)}
    if kind=="type" {
        let units=Array((a["text"] as? String ?? "").utf16)
        var offset=0
        while offset<units.count {
            try check(expected,input:true)
            var end=min(offset+16,units.count)
            if end<units.count && units[end-1]>=0xD800 && units[end-1]<=0xDBFF {end-=1}
            let text=Array(units[offset..<end])
            defer{try? keyEvent(0,false,pid,[],text)}
            try keyEvent(0,true,pid,[],text)
            offset=end
        }
        return ["typed_utf16_units":units.count]
    }
    if kind=="hotkey" || kind=="press" {
        let names=kind=="hotkey" ? (a["keys"] as? [String] ?? []) : [a["key"] as? String ?? ""]
        let codes=try names.map{ name -> CGKeyCode in guard let code=keyCodes[name.lowercased()]else{throw Failure("Unsupported macOS key: \(name)")};return code }
        for _ in 0..<(kind=="press" ? (a["presses"] as? Int ?? 1):1){
            var held:[CGKeyCode]=[];var flags:CGEventFlags=[]
            defer{for code in held.reversed(){flags.subtract(modifier(code));try? keyEvent(code,false,pid,flags)}}
            for code in codes{try check(expected,input:true);held.append(code);flags.formUnion(modifier(code));try keyEvent(code,true,pid,flags)}
        }
        return ["pressed":names]
    }
    if kind=="scroll" {
        let n=Int32(a["clicks"] as? Int ?? 0),horizontal=a["horizontal"] as? Bool ?? false
        guard let e=CGEvent(scrollWheelEvent2Source:nil,units:.line,wheelCount:2,wheel1:horizontal ? 0:n,wheel2:horizontal ? n:0,wheel3:0)else{throw Failure("Unable to create scroll event")}
        try check(expected,input:true);e.post(tap:.cgSessionEventTap);return ["scrolled":n]
    }
    let buttonName=a["button"] as? String ?? "left"
    let button:CGMouseButton=buttonName=="right" ? .right : buttonName=="middle" ? .center : .left
    let down:CGEventType=buttonName=="right" ? .rightMouseDown : buttonName=="middle" ? .otherMouseDown : .leftMouseDown
    let up:CGEventType=buttonName=="right" ? .rightMouseUp : buttonName=="middle" ? .otherMouseUp : .leftMouseUp
    if kind=="click" {
        let p=try point(a["x"] as? Int ?? -1,a["y"] as? Int ?? -1)
        for i in 1...(a["clicks"] as? Int ?? 1){
            try check(expected,input:true);if CGWarpMouseCursorPosition(p) != .success{throw Failure("Unable to move pointer")}
            defer{try? mouseEvent(up,p,button,pid,i)}
            try mouseEvent(down,p,button,pid,i)
            Thread.sleep(forTimeInterval:0.02)
            if i>1{Thread.sleep(forTimeInterval:0.04)}
        }
        return ["clicked":[Int(p.x),Int(p.y)]]
    }
    if kind=="move" || kind=="drag" {
        let from=kind=="drag" ? try point(a["start_x"] as? Int ?? -1,a["start_y"] as? Int ?? -1):position()
        let to=try point(a[kind=="drag" ? "end_x":"x"] as? Int ?? -1,a[kind=="drag" ? "end_y":"y"] as? Int ?? -1)
        let seconds=a["duration"] as? Double ?? 0.1
        if kind=="drag"{CGWarpMouseCursorPosition(from)}
        defer{if kind=="drag"{try? mouseEvent(up,position(),button,pid)}}
        if kind=="drag"{try check(expected,input:true);try mouseEvent(down,from,button,pid)}
        let steps=max(1,Int(ceil(seconds/0.02)))
        for i in 1...steps{
            try check(expected,input:true)
            let p=CGPoint(x:from.x+(to.x-from.x)*Double(i)/Double(steps),y:from.y+(to.y-from.y)*Double(i)/Double(steps))
            if CGWarpMouseCursorPosition(p) != .success{throw Failure("Unable to move pointer")}
            try mouseEvent(kind=="drag" ? (button == .right ? .rightMouseDragged:.leftMouseDragged):.mouseMoved,p,button,pid)
            if seconds>0{Thread.sleep(forTimeInterval:seconds/Double(steps))}
        }
        return ["mouse":[Int(to.x),Int(to.y)]]
    }
    throw Failure("Unknown native action: \(kind)")
}
func capture(normalize:Bool=true)throws->CGImage {
    try check()
    if !CGPreflightScreenCaptureAccess(){throw Failure("Enable Screen Recording for hosting process")}
    let cg:CGImage
    if let image=try modernCapture(){cg=image;lastCaptureBackend="screencapturekit"}
    else if #available(macOS 15.0,*) {
        cg=try commandCapture();lastCaptureBackend="system-command-fallback"
    }else if let image=legacyCapture?(CGMainDisplayID())?.takeRetainedValue(){
        cg=image;lastCaptureBackend="coregraphics-memory"
    }else{cg=try commandCapture();lastCaptureBackend="system-command-fallback"}
    if !normalize{return cg}
    let s=screenSize()
    guard let context=CGContext(data:nil,width:Int(s.width),height:Int(s.height),bitsPerComponent:8,bytesPerRow:0,space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue)else{throw Failure("Image allocation failed")}
    context.interpolationQuality = .high;context.draw(cg,in:CGRect(origin:.zero,size:s))
    guard let logical=context.makeImage()else{throw Failure("Image conversion failed")};return logical
}
func commandCapture()throws->CGImage {
    let file=URL(fileURLWithPath:NSTemporaryDirectory()).appendingPathComponent("ccc-\(UUID().uuidString).png")
    defer{try? FileManager.default.removeItem(at:file)}
    let p=Process();p.executableURL=URL(fileURLWithPath:"/usr/sbin/screencapture");p.arguments=["-x","-m",file.path];p.standardOutput=FileHandle.nullDevice;p.standardError=FileHandle.nullDevice
    try p.run();p.waitUntilExit()
    guard p.terminationStatus==0,let image=NSImage(contentsOf:file),let cg=image.cgImage(forProposedRect:nil,context:nil,hints:nil)else{throw Failure("Screenshot unavailable")}
    return cg
}
func cropped(_ image:CGImage,_ r:CGRect?)throws->CGImage {if let r=r{guard let out=image.cropping(to:r)else{throw Failure("Invalid crop")};return out};return image}
func observe(_ request:[String:Any])throws->[String:Any] {
    let expected=request["expected"] as? String;try check(expected)
    let identity=appID();let r=try rect(request["crop"])
    let screen=screenSize(),logical=r ?? CGRect(origin:.zero,size:screen)
    let raw=try capture(normalize:false)
    let sx=CGFloat(raw.width)/screen.width,sy=CGFloat(raw.height)/screen.height
    let pixels=CGRect(x:logical.minX*sx,y:logical.minY*sy,width:logical.width*sx,height:logical.height*sy)
    let image=try cropped(raw,pixels)
    try check(expected)
    if identity != appID(){throw Failure("Foreground changed during capture")}
    let profile=request["profile"] as? String ?? "ultra",format=request["format"] as? String ?? "jpeg"
    let maxWidth=profile=="ultra" ? 512:profile=="fast" ? 768:Int(logical.width)
    let w=min(maxWidth,Int(logical.width)),h=max(1,Int((logical.height*CGFloat(w)/logical.width).rounded()))
    guard let context=CGContext(data:nil,width:w,height:h,bitsPerComponent:8,bytesPerRow:0,space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue)else{throw Failure("Image allocation failed")}
    context.draw(image,in:CGRect(x:0,y:0,width:w,height:h))
    guard let cg=context.makeImage()else{throw Failure("Image resize failed")}
    let rep=NSBitmapImageRep(cgImage:cg)
    guard let data=rep.representation(using:format=="png" ? .png:.jpeg,properties:[.compressionFactor:profile=="ultra" ? 0.2:profile=="fast" ? 0.3:0.85])else{throw Failure("Image encoding failed")}
    let s=screenSize()
    return ["image":data.base64EncodedString(),"mimeType":format=="png" ? "image/png":"image/jpeg","origin":[Int(r?.minX ?? 0),Int(r?.minY ?? 0)],"logical_size":[Int(logical.width),Int(logical.height)],"image_size":[w,h],"screen_size":[Int(s.width),Int(s.height)],"app_id":identity,"capture_backend":lastCaptureBackend]
}
func attr(_ element:AXUIElement,_ key:String)->CFTypeRef?{var value:CFTypeRef?;return AXUIElementCopyAttributeValue(element,key as CFString,&value) == .success ? value:nil}
struct ElementEntry { let element:AXUIElement;let pid:pid_t;let created:Date }
var elements:[String:ElementEntry]=[:]
func remember(_ e:AXUIElement,_ pid:pid_t)->String {
    elements=elements.filter{Date().timeIntervalSince($0.value.created)<30}
    if elements.count>=512,let oldest=elements.min(by:{$0.value.created<$1.value.created})?.key{elements.removeValue(forKey:oldest)}
    let id=UUID().uuidString;elements[id]=ElementEntry(element:e,pid:pid,created:Date());return id
}
func bulk(_ e:AXUIElement,_ names:[String])->[String:Any] {
    var output:CFArray?
    if AXUIElementCopyMultipleAttributeValues(e,names as CFArray,AXCopyMultipleAttributeOptions(rawValue:0),&output) == .success,let values=output as? [Any],values.count==names.count{
        return Dictionary(uniqueKeysWithValues:zip(names,values))
    }
    var result:[String:Any]=[:];for name in names{if let value=attr(e,name){result[name]=value}};return result
}
func accessibilityRows(_ r:CGRect?)throws->[[String:Any]] {
    guard AXIsProcessTrusted(),let pid=front()?.processIdentifier else{return []}
    let app=AXUIElementCreateApplication(pid);AXUIElementSetMessagingTimeout(app,0.10)
    guard let focused=attr(app,kAXFocusedWindowAttribute)else{return []}
    var stack:[AXUIElement]=[focused as! AXUIElement],rows:[[String:Any]]=[];let end=Date(timeIntervalSinceNow:0.16);var visited=0
    let screen=screenSize()
    let names=[kAXRoleAttribute,kAXPositionAttribute,kAXSizeAttribute,kAXTitleAttribute,kAXValueAttribute,kAXDescriptionAttribute,kAXChildrenAttribute,kAXEnabledAttribute]
    while !stack.isEmpty && visited<300 && Date()<end{
        if visited%16==0{try check(String(pid))}
        let e=stack.removeLast();visited+=1
        let values=bulk(e,names),role=values[kAXRoleAttribute] as? String ?? ""
        if role=="AXSecureTextField"{continue}
        if role != "AXWindow" && role != "AXGroup",let pv=values[kAXPositionAttribute],let sv=values[kAXSizeAttribute],CFGetTypeID(pv as CFTypeRef)==AXValueGetTypeID(),CFGetTypeID(sv as CFTypeRef)==AXValueGetTypeID(){
            var pos=CGPoint.zero;var size=CGSize.zero
            if AXValueGetValue(pv as! AXValue,.cgPoint,&pos) && AXValueGetValue(sv as! AXValue,.cgSize,&size) && size.width>0 && size.height>0{
                let center=CGPoint(x:pos.x+size.width/2,y:pos.y+size.height/2)
                if center.x>=0&&center.y>=0&&center.x<screen.width&&center.y<screen.height&&(r==nil || r!.contains(center)){
                    let order=["AXTextField","AXTextArea","AXComboBox"].contains(role) ? [kAXValueAttribute,kAXTitleAttribute,kAXDescriptionAttribute]:[kAXTitleAttribute,kAXValueAttribute,kAXDescriptionAttribute]
                    for key in order{
                        if let text=values[key] as? String,!text.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,text.count<=500{
                            var actions:[String]=[]
                            if values[kAXEnabledAttribute] as? Bool != false{
                                var names:CFArray?;if AXUIElementCopyActionNames(e,&names) == .success,(names as? [String] ?? []).contains(kAXPressAction){actions.append("invoke")}
                                if ["AXTextField","AXTextArea","AXComboBox"].contains(role){
                                    var settable=DarwinBoolean(false)
                                    if AXUIElementIsAttributeSettable(e,kAXValueAttribute as CFString,&settable) == .success,settable.boolValue{actions.append("set_value")}
                                    if AXUIElementIsAttributeSettable(e,kAXFocusedAttribute as CFString,&settable) == .success,settable.boolValue{actions.append("focus_element")}
                                }
                            }
                            rows.append(["text":text,"x":Int(center.x.rounded()),"y":Int(center.y.rounded()),"role":role,"element_id":remember(e,pid),"actions":actions]);break
                        }
                    }
                }
            }
        }
        if let children=values[kAXChildrenAttribute] as? [AXUIElement]{stack.append(contentsOf:children.prefix(300))}
    }
    return rows
}
func elementAction(_ a:[String:Any],_ expected:String?)throws->[String:Any] {
    try check(expected,input:true)
    guard let id=a["element_id"] as? String,let entry=elements[id],Date().timeIntervalSince(entry.created)<30,String(entry.pid)==appID()else{throw Failure("Unknown/expired element_id; observe again")}
    let e=entry.element
    if attr(e,kAXRoleAttribute) as? String == "AXSecureTextField"{throw Failure("Secure text fields are unsupported")}
    if attr(e,kAXEnabledAttribute) as? Bool == false{throw Failure("Control is disabled")}
    AXUIElementSetMessagingTimeout(e,1.0)
    let kind=a["action"] as? String ?? "";let result:AXError
    if kind=="invoke"{
        var actions:CFArray?;guard AXUIElementCopyActionNames(e,&actions) == .success,(actions as? [String] ?? []).contains(kAXPressAction)else{throw Failure("Control does not support invoke")}
        try check(expected,input:true);result=AXUIElementPerformAction(e,kAXPressAction as CFString)
    }else{
        let attribute=kind=="set_value" ? kAXValueAttribute:kAXFocusedAttribute
        var settable=DarwinBoolean(false)
        guard AXUIElementIsAttributeSettable(e,attribute as CFString,&settable) == .success,settable.boolValue else{throw Failure("Control attribute is not writable")}
        try check(expected,input:true)
        if kind=="set_value"{result=AXUIElementSetAttributeValue(e,attribute as CFString,(a["value"] as? String ?? "") as CFString)}
        else{result=AXUIElementSetAttributeValue(e,attribute as CFString,kCFBooleanTrue)}
    }
    if result != .success{throw Failure("Native control action failed (\(result.rawValue)); it may have taken effect; never replay")}
    return ["method":"accessibility","element_id":id,"action":kind]
}
var ocrRequest:VNRecognizeTextRequest?
func ocrRows(_ r:CGRect?)throws->[[String:Any]] {
    let image=try cropped(capture(),r)
    let req=ocrRequest ?? VNRecognizeTextRequest();req.recognitionLevel = .accurate;req.recognitionLanguages=["zh-Hans","en-US"];req.usesLanguageCorrection=false;ocrRequest=req
    try VNImageRequestHandler(cgImage:image,options:[:]).perform([req])
    var rows:[[String:Any]]=[]
    for row in req.results ?? [] {
        guard let text=row.topCandidates(1).first?.string else{continue}
        let box=row.boundingBox
        let x=(r?.minX ?? 0)+box.midX*CGFloat(image.width)
        let y=(r?.minY ?? 0)+(1-box.midY)*CGFloat(image.height)
        rows.append(["text":text,"x":Int(x.rounded()),"y":Int(y.rounded())])
    }
    return rows
}
func handle(_ req:[String:Any])throws->[String:Any] {
    let op=req["op"] as? String ?? "",expected=req["expected"] as? String
    if op=="status"{let s=screenSize(),p=position();return ["width":Int(s.width),"height":Int(s.height),"mouse":[Int(p.x),Int(p.y)],"app_id":appID(),"desktop_available":available(),"accessibility":AXIsProcessTrusted(),"screen_recording":CGPreflightScreenCaptureAccess(),"coordinates":"primary-display logical pixels","capabilities":["input":true,"accessibility_text":true,"ocr":true]]}
    try check(expected,input:op=="guard" || op=="action")
    if op=="guard"{return ["ok":true]}
    if op=="focus"{
        guard let name=req["app"] as? String,let path=NSWorkspace.shared.fullPath(forApplication:name)else{throw Failure("Application not found")}
        if let running=NSWorkspace.shared.runningApplications.first(where:{$0.bundleURL?.path==path}){running.activate(options:[.activateIgnoringOtherApps])}
        else{let p=Process();p.executableURL=URL(fileURLWithPath:"/usr/bin/open");p.arguments=["-a",path];try p.run();p.waitUntilExit();if p.terminationStatus != 0{throw Failure("Application launch failed")}}
        let end=Date(timeIntervalSinceNow:2)
        while front()?.bundleURL?.path != path {try check();if Date()>end{throw Failure("App did not become foreground")};RunLoop.current.run(until:Date(timeIntervalSinceNow:0.02))}
        return ["app_id":appID()]
    }
    if op=="observe"{return try observe(req)}
    if op=="action"{return try action(req["action"] as? [String:Any] ?? [:],expected)}
    if op=="text"{
        let textStarted=ProcessInfo.processInfo.systemUptime;var ocrMS=0.0
        let r=try rect(req["region"]),identity=appID();var rows=try accessibilityRows(r);var source="accessibility"
        let target=(req["target"] as? String)?.filter{!$0.isWhitespace}
        // Let queued target-app updates settle through bounded AX polling before
        // spending time on OCR. No cached text is reused across observations.
        let end=Date(timeIntervalSinceNow:(req["accessibility_only"] as? Bool ?? false) ? 0.05:0.35)
        while (rows.isEmpty || (target != nil && !rows.contains(where:{($0["text"] as? String ?? "").filter{!$0.isWhitespace}==target!}))) && Date()<end{
            try check(expected);RunLoop.current.run(until:Date(timeIntervalSinceNow:0.012));rows=try accessibilityRows(r)
        }
        if !(req["accessibility_only"] as? Bool ?? false) && (rows.isEmpty || (target != nil && !rows.contains{($0["text"] as? String ?? "").filter{!$0.isWhitespace}==target!})){
            let started=ProcessInfo.processInfo.systemUptime;rows=try ocrRows(r);ocrMS=(ProcessInfo.processInfo.systemUptime-started)*1000;source="ocr"
            // Native events are queued by the target app. Re-read AX after OCR
            // rather than rejecting a newly updated field based on an older AX value.
            if let target=target,!rows.contains(where:{($0["text"] as? String ?? "").filter{!$0.isWhitespace}==target}){
                let fresh=try accessibilityRows(r)
                if fresh.contains(where:{($0["text"] as? String ?? "").filter{!$0.isWhitespace}==target}){rows=fresh;source="accessibility"}
            }
        }
        try check(expected);if identity != appID(){throw Failure("Foreground changed during text extraction")}
        return ["rows":rows,"source":source,"timing":["ocr_ms":Int(ocrMS.rounded()),"total_ms":Int(((ProcessInfo.processInfo.systemUptime-textStarted)*1000).rounded())]]
    }
    throw Failure("Unknown native operation")
}
while let line=readLine(){
    var id:Any=NSNull()
    do{
        guard let data=line.data(using:.utf8),let request=try JSONSerialization.jsonObject(with:data) as? [String:Any]else{throw Failure("Invalid JSON request")}
        id=request["id"] ?? NSNull();let result=try handle(request)
        let output=try JSONSerialization.data(withJSONObject:["id":id,"ok":true,"result":result],options:[.sortedKeys])
        print(String(data:output,encoding:.utf8)!);fflush(stdout)
    }catch{
        let data=try! JSONSerialization.data(withJSONObject:["id":id,"ok":false,"error":String(describing:error)])
        print(String(data:data,encoding:.utf8)!);fflush(stdout)
    }
}
