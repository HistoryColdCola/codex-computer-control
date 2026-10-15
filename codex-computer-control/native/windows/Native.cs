using System;
using System.IO;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Automation;
using System.Web.Script.Serialization;

public static class ComputerControl {
    static readonly JavaScriptSerializer Json=new JavaScriptSerializer { MaxJsonLength=64*1024*1024 };
    static readonly string Data=Environment.GetEnvironmentVariable("CCC_DATA_DIR") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"codex-computer-control");
    static readonly string Stop=Path.Combine(Data,"STOP");
    [StructLayout(LayoutKind.Sequential)] struct POINT { public int X,Y; }
    [StructLayout(LayoutKind.Sequential)] struct RECT { public int Left,Top,Right,Bottom; }
    [StructLayout(LayoutKind.Sequential)] struct MOUSEINPUT { public int dx,dy;public uint mouseData,dwFlags,time;public IntPtr dwExtraInfo; }
    [StructLayout(LayoutKind.Sequential)] struct KEYBDINPUT { public ushort wVk,wScan;public uint dwFlags,time;public IntPtr dwExtraInfo; }
    [StructLayout(LayoutKind.Explicit)] struct INPUTUNION { [FieldOffset(0)]public MOUSEINPUT mi;[FieldOffset(0)]public KEYBDINPUT ki; }
    [StructLayout(LayoutKind.Sequential)] struct INPUT { public uint type;public INPUTUNION data; }
    [DllImport("user32.dll",SetLastError=true)] static extern uint SendInput(uint n,INPUT[] input,int size);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h,int cmd);
    [DllImport("user32.dll")] static extern bool GetCursorPos(out POINT p);
    [DllImport("user32.dll")] static extern bool SetCursorPos(int x,int y);
    [DllImport("user32.dll")] static extern int GetSystemMetrics(int index);
    [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] static extern bool SetProcessDpiAwarenessContext(IntPtr context);
    [DllImport("user32.dll")] static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
    [DllImport("user32.dll",SetLastError=true)] static extern IntPtr OpenInputDesktop(uint flags,bool inherit,uint access);
    [DllImport("user32.dll")] static extern bool CloseDesktop(IntPtr h);
    [DllImport("user32.dll")] static extern bool SwitchDesktop(IntPtr h);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern bool GetUserObjectInformation(IntPtr h,int index,System.Text.StringBuilder info,int length,out int needed);
    static void EnableDpi(){try{SetThreadDpiAwarenessContext(new IntPtr(-4));}catch(EntryPointNotFoundException){SetProcessDPIAware();}}
    static ComputerControl(){try{SetProcessDpiAwarenessContext(new IntPtr(-4));}catch(EntryPointNotFoundException){SetProcessDPIAware();}EnableDpi();}
    static Dictionary<string,object> Obj(params object[] pairs){var o=new Dictionary<string,object>();for(int i=0;i<pairs.Length;i+=2)o[(string)pairs[i]]=pairs[i+1];return o;}
    static object Get(Dictionary<string,object> d,string k,object fallback){object v;return d.TryGetValue(k,out v)&&v!=null?v:fallback;}
    static int Num(Dictionary<string,object>d,string k,int fallback){return Convert.ToInt32(Get(d,k,fallback));}
    static double Real(Dictionary<string,object>d,string k,double fallback){return Convert.ToDouble(Get(d,k,fallback));}
    static string Str(Dictionary<string,object>d,string k,string fallback){return Convert.ToString(Get(d,k,fallback));}
    static int Width{get{EnableDpi();return GetSystemMetrics(0);}} static int Height{get{EnableDpi();return GetSystemMetrics(1);}}
    static string AppID{get{uint p;GetWindowThreadProcessId(GetForegroundWindow(),out p);return p==0?"":p.ToString();}}
    static bool Available(){
        if(!Environment.UserInteractive)return false;
        IntPtr h=OpenInputDesktop(0,false,0x101);if(h==IntPtr.Zero)return false;
        try {int needed;var name=new System.Text.StringBuilder(256);return GetUserObjectInformation(h,2,name,512,out needed)&&name.ToString().Equals("Default",StringComparison.OrdinalIgnoreCase)&&SwitchDesktop(h);}finally{CloseDesktop(h);}
    }
    static void Check(string expected,bool input){
        EnableDpi();
        if(File.Exists(Stop))throw new Exception("Emergency stop active");
        int parent; if(Int32.TryParse(Environment.GetEnvironmentVariable("CCC_PARENT_PID"),out parent)){try{if(Process.GetProcessById(parent).HasExited)throw new Exception();}catch{throw new Exception("Controller disconnected");}}
        if(!Available())throw new Exception("Interactive desktop locked or unavailable");
        if(!String.IsNullOrEmpty(expected)&&AppID!=expected)throw new Exception("Foreground app changed; do not replay input");
        POINT p;GetCursorPos(out p);if(input&&p.X<=0&&p.Y<=0)throw new Exception("Pointer at emergency stop corner");
    }
    static void Point(int x,int y){if(x<0||y<0||x>=Width||y>=Height||(x==0&&y==0))throw new Exception("Point outside primary display or stop corner");}
    static Rectangle Region(Dictionary<string,object> r){
        if(r==null)return new Rectangle(0,0,Width,Height);
        var box=new Rectangle(Num(r,"x",-1),Num(r,"y",-1),Num(r,"width",0),Num(r,"height",0));
        if(box.X<0||box.Y<0||box.Width<=0||box.Height<=0||box.Right>Width||box.Bottom>Height)throw new Exception("Region outside primary display");return box;
    }
    static void Send(INPUT e){if(SendInput(1,new INPUT[]{e},Marshal.SizeOf(typeof(INPUT)))!=1)throw new Exception("SendInput rejected input (possibly UIPI/integrity level); no elevation bypass");}
    static void Key(ushort vk,bool down,bool unicode){var e=new INPUT();e.type=1;e.data.ki.wVk=unicode?(ushort)0:vk;e.data.ki.wScan=unicode?vk:(ushort)0;
        bool extended=(!unicode&&((vk>=0x21&&vk<=0x2e)||(vk>=0x5b&&vk<=0x5c)));
        e.data.ki.dwFlags=(down?0u:2u)|(unicode?4u:0u)|(extended?1u:0u);Send(e);}
    static void Mouse(uint flags,int data){var e=new INPUT();e.type=0;e.data.mi.dwFlags=flags;e.data.mi.mouseData=unchecked((uint)data);Send(e);}
    static ushort Code(string name){
        name=name.ToLowerInvariant();
        var map=new Dictionary<string,ushort>{{"command",0x5b},{"cmd",0x5b},{"meta",0x5b},{"win",0x5b},{"windows",0x5b},{"shift",0x10},{"ctrl",0x11},{"control",0x11},{"alt",0x12},{"option",0x12},{"enter",0x0d},{"return",0x0d},{"esc",0x1b},{"escape",0x1b},{"tab",9},{"space",0x20},{"backspace",8},{"delete",0x2e},{"insert",0x2d},{"up",0x26},{"down",0x28},{"left",0x25},{"right",0x27},{"home",0x24},{"end",0x23},{"pageup",0x21},{"pagedown",0x22}};
        ushort value;if(map.TryGetValue(name,out value))return value;
        if(name.Length==1&&Char.IsLetterOrDigit(name[0])&&name[0]<128)return (ushort)Char.ToUpperInvariant(name[0]);
        int n;if(name.StartsWith("f")&&Int32.TryParse(name.Substring(1),out n)&&n>=1&&n<=12)return (ushort)(0x6f+n);
        throw new Exception("Unsupported Windows key: "+name);
    }
    sealed class Entry { public AutomationElement Element;public string Pid;public DateTime Created; }
    static readonly Dictionary<string,Entry> Elements=new Dictionary<string,Entry>();
    static string Remember(AutomationElement element){
        var stale=new List<string>();foreach(var pair in Elements)if((DateTime.UtcNow-pair.Value.Created).TotalSeconds>30)stale.Add(pair.Key);
        foreach(string id in stale)Elements.Remove(id);
        if(Elements.Count>=512){string oldest=null;DateTime time=DateTime.MaxValue;foreach(var pair in Elements)if(pair.Value.Created<time){oldest=pair.Key;time=pair.Value.Created;}if(oldest!=null)Elements.Remove(oldest);}
        string token=Guid.NewGuid().ToString("N");Elements[token]=new Entry{Element=element,Pid=AppID,Created=DateTime.UtcNow};return token;
    }
    static object ElementAction(Dictionary<string,object>a,string expected){
        Check(expected,true);string id=Str(a,"element_id","");Entry entry;
        if(!Elements.TryGetValue(id,out entry)||(DateTime.UtcNow-entry.Created).TotalSeconds>30||entry.Pid!=AppID)throw new Exception("Unknown/expired element_id; observe again");
        var e=entry.Element;var info=e.Current;if(info.IsPassword||info.IsOffscreen||!info.IsEnabled)throw new Exception("Control is secure, unavailable or disabled");
        string kind=Str(a,"action","");object pattern;Check(expected,true);
        if(kind=="invoke"){
            if(!e.TryGetCurrentPattern(InvokePattern.Pattern,out pattern))throw new Exception("Control does not support invoke");
            ((InvokePattern)pattern).Invoke();
        }else if(kind=="set_value"){
            if(!e.TryGetCurrentPattern(ValuePattern.Pattern,out pattern)||((ValuePattern)pattern).Current.IsReadOnly)throw new Exception("Control does not support writable value");
            ((ValuePattern)pattern).SetValue(Str(a,"value",""));
        }else e.SetFocus();
        return Obj("method","uia","element_id",id,"action",kind);
    }
    static object Act(Dictionary<string,object>a,string expected){
        Check(expected,true);string kind=Str(a,"action","");
        if(kind=="invoke"||kind=="set_value"||kind=="focus_element")return ElementAction(a,expected);
        if(kind=="type"){
            string text=Str(a,"text","");foreach(char ch in text){Check(expected,true);try{Key(ch,true,true);}finally{Key(ch,false,true);}}
            return Obj("typed_utf16_units",text.Length);
        }
        if(kind=="press"||kind=="hotkey"){
            object[] names=kind=="press"?new object[]{Str(a,"key","")}:(object[])a["keys"];
            var codes=new List<ushort>();foreach(object name in names)codes.Add(Code((string)name));
            for(int i=0;i<(kind=="press"?Num(a,"presses",1):1);i++){
                var held=new List<ushort>();Exception releaseError=null;
                try{foreach(ushort code in codes){Check(expected,true);held.Add(code);Key(code,true,false);}}
                finally{held.Reverse();foreach(ushort code in held){try{Key(code,false,false);}catch(Exception e){releaseError=releaseError??e;}}if(releaseError!=null)throw releaseError;}
            }
            return Obj("pressed",names);
        }
        if(kind=="scroll"){Check(expected,true);Mouse(Convert.ToBoolean(Get(a,"horizontal",false))?0x1000u:0x800u,Num(a,"clicks",0)*120);return Obj("scrolled",Num(a,"clicks",0));}
        string button=Str(a,"button","left");uint down=button=="right"?8u:button=="middle"?0x20u:2u;uint up=down<<1;
        if(kind=="click"){
            int x=Num(a,"x",-1),y=Num(a,"y",-1);Point(x,y);
            for(int i=0;i<Num(a,"clicks",1);i++){Check(expected,true);if(!SetCursorPos(x,y))throw new Exception("Pointer movement failed");try{Mouse(down,0);}finally{Mouse(up,0);}if(i+1<Num(a,"clicks",1))Thread.Sleep(50);}
            return Obj("clicked",new int[]{x,y});
        }
        if(kind=="move"||kind=="drag"){
            POINT from;GetCursorPos(out from);if(kind=="drag"){from.X=Num(a,"start_x",-1);from.Y=Num(a,"start_y",-1);Point(from.X,from.Y);}
            int x=Num(a,kind=="drag"?"end_x":"x",-1),y=Num(a,kind=="drag"?"end_y":"y",-1);Point(x,y);
            double duration=Real(a,"duration",.1);int steps=Math.Max(1,(int)Math.Ceiling(duration/.02));
            if(kind=="drag"&&!SetCursorPos(from.X,from.Y))throw new Exception("Pointer movement failed");
            try{if(kind=="drag"){Check(expected,true);Mouse(down,0);}for(int i=1;i<=steps;i++){Check(expected,true);if(!SetCursorPos(from.X+(int)Math.Round((x-from.X)*(double)i/steps),from.Y+(int)Math.Round((y-from.Y)*(double)i/steps)))throw new Exception("Pointer movement failed");if(duration>0)Thread.Sleep((int)(duration*1000/steps));}}
            finally{if(kind=="drag")Mouse(up,0);}
            return Obj("mouse",new int[]{x,y});
        }
        throw new Exception("Unknown native action");
    }
    static Bitmap Capture(Rectangle r){
        Check(null,false);var b=new Bitmap(r.Width,r.Height,PixelFormat.Format32bppArgb);
        try{using(var g=Graphics.FromImage(b)){g.CopyFromScreen(r.X,r.Y,0,0,r.Size,CopyPixelOperation.SourceCopy);}return b;}catch{b.Dispose();throw;}
    }
    static object Observe(Dictionary<string,object> req){
        string expected=Str(req,"expected",null);Check(expected,false);string identity=AppID;
        var r=Region(Get(req,"crop",null) as Dictionary<string,object>);string profile=Str(req,"profile","ultra"),format=Str(req,"format","jpeg");
        using(var full=Capture(r)){
            int w=Math.Min(full.Width,profile=="ultra"?512:profile=="fast"?768:full.Width),h=Math.Max(1,(int)Math.Round(full.Height*(double)w/full.Width));
            using(var scaled=new Bitmap(w,h))using(var mem=new MemoryStream()){
                using(var g=Graphics.FromImage(scaled)){g.DrawImage(full,0,0,w,h);}
                if(format=="png")scaled.Save(mem,ImageFormat.Png);
                else{ImageCodecInfo codec=null;foreach(var c in ImageCodecInfo.GetImageEncoders())if(c.MimeType=="image/jpeg")codec=c;
                    using(var ep=new EncoderParameters(1)){ep.Param[0]=new EncoderParameter(System.Drawing.Imaging.Encoder.Quality,profile=="ultra"?20L:profile=="fast"?30L:85L);scaled.Save(mem,codec,ep);}}
                Check(expected,false);if(identity!=AppID)throw new Exception("Foreground changed during capture");
                return Obj("image",Convert.ToBase64String(mem.ToArray()),"mimeType",format=="png"?"image/png":"image/jpeg","origin",new int[]{r.X,r.Y},"logical_size",new int[]{r.Width,r.Height},"image_size",new int[]{w,h},"screen_size",new int[]{Width,Height},"app_id",identity);
            }
        }
    }
    static List<Dictionary<string,object>> TextRows(Dictionary<string,object> req){
        var region=Region(Get(req,"region",null) as Dictionary<string,object>);var rows=new List<Dictionary<string,object>>();
        var window=AutomationElement.FromHandle(GetForegroundWindow());if(window==null)return rows;
        var cache=new CacheRequest();cache.TreeScope=TreeScope.Element;
        foreach(var property in new AutomationProperty[]{AutomationElement.NameProperty,AutomationElement.IsPasswordProperty,AutomationElement.IsOffscreenProperty,AutomationElement.IsEnabledProperty,AutomationElement.BoundingRectangleProperty,AutomationElement.ControlTypeProperty,AutomationElement.IsKeyboardFocusableProperty,AutomationElement.IsInvokePatternAvailableProperty,ValuePattern.ValueProperty,ValuePattern.IsReadOnlyProperty})cache.Add(property);
        cache.Add(ValuePattern.Pattern);
        var queue=new Queue<AutomationElement>();queue.Enqueue(window);int visited=0;var clock=Stopwatch.StartNew();var walker=TreeWalker.ControlViewWalker;
        while(queue.Count>0&&visited++<250&&clock.ElapsedMilliseconds<250){
            var e=queue.Dequeue();
            try{
                var cached=e.GetUpdatedCache(cache);var info=cached.Cached;if(info.IsPassword||info.IsOffscreen)continue;
                var box=info.BoundingRectangle;
                if(box.Width>0&&box.Height>0){int x=(int)Math.Round(box.X+box.Width/2),y=(int)Math.Round(box.Y+box.Height/2);
                    if(region.Contains(x,y)&&x>=0&&y>=0&&x<Width&&y<Height&&info.ControlType!=ControlType.Window&&info.ControlType!=ControlType.Pane){
                        string text=info.Name;object pattern;
                        var actions=new List<string>();
                        if(cached.TryGetCachedPattern(ValuePattern.Pattern,out pattern)){var valuePattern=((ValuePattern)pattern).Cached;string value=valuePattern.Value;if(!String.IsNullOrWhiteSpace(value))text=value;if(info.IsEnabled&&!valuePattern.IsReadOnly)actions.Add("set_value");}
                        if(info.IsEnabled&&Convert.ToBoolean(cached.GetCachedPropertyValue(AutomationElement.IsInvokePatternAvailableProperty)))actions.Add("invoke");
                        if(info.IsEnabled&&info.IsKeyboardFocusable)actions.Add("focus_element");
                        if(!String.IsNullOrWhiteSpace(text)&&text.Length<=500)rows.Add(Obj("text",text,"x",x,"y",y,"role",info.ControlType.ProgrammaticName,"element_id",Remember(e),"actions",actions.ToArray()));
                    }
                }
                var child=walker.GetFirstChild(e);int n=0;while(child!=null&&n++<250&&queue.Count<250){queue.Enqueue(child);child=walker.GetNextSibling(child);}
            }catch(ElementNotAvailableException){}
        }
        return rows;
    }
    public static string SaveOcrImage(string request,string file){
        var req=Json.Deserialize<Dictionary<string,object>>(request);Check(Str(req,"expected",null),false);
        var r=Region(Get(req,"region",null) as Dictionary<string,object>);using(var image=Capture(r)){image.Save(file,ImageFormat.Png);}return Json.Serialize(new int[]{r.X,r.Y});
    }
    public static void Guard(string expected){Check(expected,false);}
    public static string Dispatch(string line){
        var req=Json.Deserialize<Dictionary<string,object>>(line);object id=Get(req,"id",null);
        try{
            string op=Str(req,"op",""),expected=Str(req,"expected",null);object result;
            if(op=="status"){
                POINT p;GetCursorPos(out p);bool desktop=Available();result=Obj("width",Width,"height",Height,"mouse",new int[]{p.X,p.Y},"app_id",AppID,"desktop_available",desktop,"accessibility",desktop,"screen_recording",desktop,"coordinates","primary-display physical pixels (DPI aware)","capabilities",Obj("input",true,"accessibility_text",true,"ocr","windows-ocr-when-available"));
            }else{
                Check(expected,op=="guard"||op=="action");
                if(op=="guard")result=Obj("ok",true);
                else if(op=="action")result=Act((Dictionary<string,object>)req["action"],expected);
                else if(op=="observe")result=Observe(req);
                else if(op=="text"||op=="text_accessibility")result=Obj("rows",TextRows(req),"source","uia");
                else if(op=="focus"){
                    string name=Str(req,"app","");string stem=Path.GetFileNameWithoutExtension(name);var matches=new List<Process>();foreach(var process in Process.GetProcessesByName(stem))if(process.MainWindowHandle!=IntPtr.Zero)matches.Add(process);
                    if(matches.Count>1)throw new Exception("Multiple matching applications; focus desired window manually and omit app");
                    if(matches.Count==0){if(!name.EndsWith(".exe",StringComparison.OrdinalIgnoreCase)||name.Contains("\"")||name.Contains("\n"))throw new Exception("To launch a Windows app use an executable name/path ending in .exe");Process.Start(new ProcessStartInfo(name){UseShellExecute=false});var until=DateTime.UtcNow.AddSeconds(2);while(DateTime.UtcNow<until){Check(null,false);foreach(var process in Process.GetProcessesByName(stem))if(process.MainWindowHandle!=IntPtr.Zero)matches.Add(process);if(matches.Count>0)break;Thread.Sleep(30);}}
                    if(matches.Count!=1)throw new Exception("No unique application window found");var target=matches[0];ShowWindow(target.MainWindowHandle,9);SetForegroundWindow(target.MainWindowHandle);
                    var deadline=DateTime.UtcNow.AddSeconds(2);while(AppID!=target.Id.ToString()){Check(null,false);if(DateTime.UtcNow>deadline)throw new Exception("Windows refused foreground activation");Thread.Sleep(20);}result=Obj("app_id",AppID);
                }else throw new Exception("Unknown native operation");
            }
            return Json.Serialize(Obj("id",id,"ok",true,"result",result));
        }catch(Exception e){return Json.Serialize(Obj("id",id,"ok",false,"error",e.Message));}
    }
}
