#!/usr/bin/env python3
import math, os, random, subprocess, sys, tempfile, shutil, json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

if len(sys.argv) != 4:
    raise SystemExit('usage: render-socksnode-recreate-fast.py <reference.mp4> <output.mp4> <analysis.json>')
ref=Path(sys.argv[1]); out=Path(sys.argv[2]); analysis=Path(sys.argv[3])
out.parent.mkdir(parents=True,exist_ok=True); analysis.parent.mkdir(parents=True,exist_ok=True)
W,H,FPS=720,1280,30
DUR=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(ref)],text=True).strip())
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONTB='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
F18=ImageFont.truetype(FONT,18); F20=ImageFont.truetype(FONT,20); F22=ImageFont.truetype(FONT,22)
F24=ImageFont.truetype(FONT,24); F28=ImageFont.truetype(FONTB,28); F34=ImageFont.truetype(FONTB,34)
GREEN=(47,224,135); GREEN2=(75,239,161)
random.seed(7)

def rr(draw,box,r,fill,outline=None,width=1): draw.rounded_rectangle(box,radius=r,fill=fill,outline=outline,width=width)
def text_center(draw,xy,txt,font,fill,stroke=0,stroke_fill=(0,0,0)):
    bb=draw.multiline_textbbox((0,0),txt,font=font,align='center',spacing=0,stroke_width=stroke)
    x=xy[0]-(bb[2]-bb[0])/2; y=xy[1]-(bb[3]-bb[1])/2
    draw.multiline_text((x,y),txt,font=font,fill=fill,align='center',spacing=0,stroke_width=stroke,stroke_fill=stroke_fill)

def logo(draw,x,y,scale=1.0,with_text=True):
    r=max(2,int(5*scale)); lw=max(2,int(4*scale)); c=GREEN2
    pts=[(x+8*scale,y+10*scale),(x+32*scale,y+10*scale),(x+32*scale,y+28*scale),(x+12*scale,y+28*scale),(x+12*scale,y+45*scale),(x+36*scale,y+45*scale)]
    for a,b in zip(pts[:-1],pts[1:]): draw.line([a,b],fill=c,width=lw)
    for px,py in [pts[0],pts[2],pts[-1]]: draw.ellipse((px-r,py-r,px+r,py+r),fill=(8,20,25),outline=c,width=max(1,int(2*scale)))
    if with_text:
        f=ImageFont.truetype(FONTB,max(12,int(22*scale)))
        draw.text((x+48*scale,y+8*scale),'Socks',font=f,fill=(180,196,203))
        draw.text((x+48*scale,y+31*scale),'Node',font=f,fill=c)

def glow_blob(img,cx,cy,rx,ry,color,alpha):
    layer=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(layer)
    d.ellipse((cx-rx,cy-ry,cx+rx,cy+ry),fill=(*color,alpha))
    layer=layer.filter(ImageFilter.GaussianBlur(radius=max(rx,ry)//2))
    return Image.alpha_composite(img.convert('RGBA'),layer)

def dashboard_flat():
    im=Image.new('RGB',(660,930),(16,22,28)); d=ImageDraw.Draw(im)
    d.rectangle((0,0,660,42),fill=(25,31,37))
    for i,c in enumerate([(236,86,86),(236,192,86),(85,205,124)]): d.ellipse((14+i*18,13,24+i*18,23),fill=c)
    d.text((85,10),'AdsPower  /  Proxies',font=F18,fill=(205,214,220))
    d.text((22,58),'Profiles',font=F28,fill=(230,235,238)); rr(d,(520,55,640,91),10,(35,141,106)); d.text((550,62),'New Profile',font=F18,fill='white')
    d.text((24,112),'Name',font=F18,fill=(139,153,162)); d.text((355,112),'Proxy',font=F18,fill=(139,153,162)); d.text((520,112),'Status',font=F18,fill=(139,153,162))
    names=['FB_Acc_01','FB_Acc_07','FB_Acc_08','FB_Profile_Layer','IG_Profile_02','FB_Sumith_09','FB_Recover_03','Tiktok_01','FB_Account_17','FB_Acc_19','Profile_115','Clone_Set_3','FB_Profile_03']
    statuses=['Banned','Checkpoint Required','Banned','Checkpoint Required','Banned','Banned','Checkpoint Required','Banned','Checkpoint Required','Banned','Banned','Checkpoint Required','Banned']
    for i in range(13):
        y=145+i*56
        if i%2==0: d.rectangle((12,y-7,648,y+43),fill=(19,27,33))
        d.ellipse((24,y,52,y+28),fill=((50+13*i)%170+50,(90+27*i)%130+70,(110+19*i)%120+80))
        d.text((66,y+2),names[i],font=F18,fill=(218,224,228)); d.text((355,y+2),f'{121+i}.{50+i}.0.{10+i}',font=F18,fill=(162,174,181))
        w=116 if statuses[i]=='Banned' else 164
        x=500 if w==116 else 456
        rr(d,(x,y-2,x+w,y+30),13,(212,69,70)); d.text((x+13,y+3),statuses[i],font=ImageFont.truetype(FONTB,15),fill=(255,224,224))
    d.rectangle((575,130,655,900),fill=(13,19,24)); d.text((589,145),'Proxy',font=F18,fill=(206,216,222))
    for k in range(8):
        yy=188+k*82; d.text((588,yy),'Error',font=F18,fill=(231,92,92)); d.text((588,yy+22),f'{95+k} ms',font=F18,fill=(130,145,154))
    return im
BASE_DASH=dashboard_flat()

def phase1(t):
    yy=np.linspace(0,1,H)[:,None,None]; top=np.array([90,71,55],dtype=float); bot=np.array([18,22,25],dtype=float)
    arr=np.repeat((top*(1-yy)+bot*yy),W,axis=1).astype(np.uint8)
    im=Image.fromarray(arr,'RGB').convert('RGBA'); d=ImageDraw.Draw(im)
    d.rectangle((0,1030,W,H),fill=(30,28,25,255)); d.rectangle((70,1100,670,1160),fill=(12,14,16,255))
    dash=BASE_DASH.copy().resize((650,915),Image.Resampling.LANCZOS)
    dash=dash.rotate(-1.6+0.8*math.sin(t*0.7),resample=Image.Resampling.BICUBIC,expand=True,fillcolor=(8,10,12))
    scale=1.02+0.015*math.sin(t*0.9); dash=dash.resize((int(dash.width*scale),int(dash.height*scale)),Image.Resampling.LANCZOS)
    im.alpha_composite(dash.convert('RGBA'),(-20+int(12*math.sin(t*1.4)),80+int(10*math.sin(t*1.1+1))))
    ring=Image.new('RGBA',(W,H),(0,0,0,0)); rd=ImageDraw.Draw(ring); cx=315+22*math.sin(t*0.8); cy=430+18*math.sin(t*0.7)
    for j,a in [(0,40),(7,28),(16,14)]: rd.arc((cx-155-j,cy-155-j,cx+155+j,cy+155+j),200,345,fill=(255,194,126,a),width=10)
    ring=ring.filter(ImageFilter.GaussianBlur(5)); return Image.alpha_composite(im,ring).convert('RGB')

def grid_background(t):
    im=Image.new('RGBA',(W,H),(7,16,22,255)); im=glow_blob(im,120+70*math.sin(t*0.4),250,230,310,(0,98,150),100); im=glow_blob(im,600+60*math.sin(t*0.45+1),720,250,360,(0,212,123),95)
    d=ImageDraw.Draw(im)
    for i in range(-8,10): d.line([(360,610),(360+i*70,1280)],fill=(35,110,100,70),width=1)
    for j in range(9):
        y=700+j*72; d.line([(0,y),(720,y+int((y-700)*0.10))],fill=(43,94,104,55),width=1)
    for k in range(45):
        x=(k*137+int(t*13))%W; y=(k*211)%H; d.ellipse((x,y,x+2,y+2),fill=(86,208,170,70))
    return im

def product_card(t):
    im=grid_background(t); d=ImageDraw.Draw(im)
    rr(d,(63,173,288,398),25,(16,32,39,220),(46,86,88,180),1); logo(d,94,205,0.72); rr(d,(82,297,267,350),14,(19,47,49,230)); d.text((103,312),'Quick Node',font=F20,fill=(142,205,185))
    rr(d,(438,220,665,492),25,(13,27,34,220),(45,72,76,180),1); d.text((462,246),'Proview',font=F20,fill=(150,164,172)); d.text((463,287),'Active',font=F22,fill=GREEN2)
    for k,h in enumerate([35,52,28,64,42]): d.rectangle((470+k*30,400-h,484+k*30,400),fill=(34,154,116,180))
    rr(d,(160,115,575,1070),30,(13,24,30,236),(45,92,88,220),2); logo(d,196,150,0.9); d.text((490,154),'•••',font=F28,fill=(94,118,127))
    cx,cy=285,370; d.arc((cx-92,cy-92,cx+92,cy+92),0,360,fill=(45,69,75),width=14); frac=0.52+0.04*math.sin(t*0.8); d.arc((cx-92,cy-92,cx+92,cy+92),-90,-90+360*frac,fill=GREEN2,width=14); text_center(d,(cx,cy),'0.5%',F34,(225,236,235))
    d.text((410,320),'Session',font=F18,fill=(132,150,158)); d.text((410,350),'Stable',font=F22,fill=(215,226,229))
    y=505
    for title in ['Series','Carrier','Center']:
        d.text((195,y),title,font=F20,fill=(199,212,214)); d.line((195,y+38,540,y+38),fill=(40,63,68),width=1); y+=164
    rr(d,(345,540,540,590),11,(18,39,44),(42,92,82),1); d.text((362,553),'All Carriers',font=F18,fill=(203,217,217))
    rr(d,(345,704,540,754),11,(18,39,44),(42,92,82),1); d.text((362,717),'California' if t<13.0 else 'Texas',font=F18,fill=(203,217,217))
    rr(d,(345,868,540,918),11,(18,39,44),(42,92,82),1); d.text((362,881),'United States',font=F18,fill=(203,217,217))
    if 11.2<t<13.0:
        rr(d,(320,750,560,920),14,(15,31,36,245),(54,100,89),1)
        for i,s in enumerate(['California','New York','Texas']): d.text((345,775+i*42),s,font=F18,fill=(217,228,229))
    if 14.0<t<16.7:
        rr(d,(300,520,565,880),14,(15,31,36,248),(54,100,89),1)
        for i,s in enumerate(['T-Mobile 5G','Verizon 5G','AT&T 5G','AT&T 5G','Renatel 5G','Audiolab 5G','Recieve 5G']): d.text((325,545+i*43),s,font=F18,fill=(217,228,229))
    if t>18.0:
        rr(d,(150,975,585,1045),18,(28,124,88,245),(73,219,159),2); d.text((178,996),'Status: Connected · Texas AT&T 5G',font=F18,fill=(225,255,242))
    px=485+70*math.sin((t-10)*0.8); py=690+140*math.sin((t-10)*0.55); d.polygon([(px,py),(px+25,py+11),(px+12,py+16),(px+20,py+36),(px+10,py+40),(px+3,py+20),(px-7,py+28)],fill='white',outline=(20,30,30))
    return im.convert('RGB')

def outro(t):
    im=Image.new('RGBA',(W,H),(5,12,18,255)); im=glow_blob(im,155,360,210,420,(21,81,180),100); im=glow_blob(im,550,545,220,420,(21,220,124),105); d=ImageDraw.Draw(im)
    for k in range(55):
        x=(k*113)%W; y=(k*197+int(t*20))%H; a=70+(k%4)*30; d.ellipse((x,y,x+2,y+2),fill=(167,226,214,a))
    if t>26.6:
        for j in range(4):
            q=(t-26.6)*0.75-j*0.18
            if q>0:
                r=55+q*95; a=max(0,int(115-55*q)); d.ellipse((360-r,640-r,360+r,640+r),fill=(46,213,127,a//5),outline=(63,236,150,a),width=3)
    logo(d,240,480,1.45,True); rr(d,(195,770,525,844),30,(45,202,120,255)); text_center(d,(360,807),'Get Started',F28,'white')
    if t>25.6:
        q=min(1,(t-25.6)/1.5); px=650+(365-650)*q; py=930+(812-930)*q; d.polygon([(px,py),(px+36,py+14),(px+16,py+22),(px+28,py+51),(px+14,py+56),(px+2,py+28),(px-13,py+40)],fill='white',outline=(35,40,43))
    return im.convert('RGB')

caps=[(0.0,2.8,'NUÔI 100 ACC DIE SẠCH 99\nVÌ IP BẨN'),(2.8,4.6,'dùng Proxy Mobile thì đỉnh cao'),(4.6,6.4,'dừng lại ngay'),(6.4,9.2,'chúng tôi đã có giải pháp cá nhân\ntại Việt Nam'),(9.2,11.6,'Proxy Mobile chất lượng y hệt'),(11.6,13.8,'nhưng giá rẻ hơn tới 10 lần'),(13.8,17.4,'đổi quốc gia, bang, IP tùy ý\nkhông giới hạn'),(17.4,21.6,'có ngay 100.000.000 IP toàn cầu\nchỉ từ 0,3 đô trên 1GB'),(21.6,24.7,'truy cập ngay socksnode.com để nhận ưu đãi'),(24.7,27.6,'link mình để ở phần mô tả')]
def caption_for(t):
    for a,b,s in caps:
        if a<=t<b:return s
    return ''
def add_overlays(im,t):
    im=im.convert('RGBA'); d=ImageDraw.Draw(im); cap=caption_for(t)
    if cap:
        f=F28 if '\n' in cap else F24; text_center(d,(360,1075 if t<20 else 1025),cap,f,GREEN,stroke=2,stroke_fill=(0,0,0))
    rr(d,(650,1170,700,1220),4,(242,247,246,245)); logo(d,658,1178,0.38,False)
    vig=Image.new('RGBA',(W,H),(0,0,0,0)); ImageDraw.Draw(vig).rectangle((0,0,W,H),outline=(0,0,0,80),width=26)
    return Image.alpha_composite(im,vig).convert('RGB')

work=Path(tempfile.mkdtemp(prefix='socksnode-recreate-'))
try:
    bounds=[0,2.8,4.6,6.4,9.2,10.0,11.6,13.8,17.4,20.0,21.6,24.7,27.6,28.4,29.2,DUR]
    items=[]
    for i,(a,b) in enumerate(zip(bounds[:-1],bounds[1:]),1):
        if b<=a: continue
        t=(a+b)/2; frame=phase1(t) if t<10 else product_card(t) if t<20 else outro(t); frame=add_overlays(frame,t)
        img=work/f'seg-{i:02d}.png'; frame.save(img,optimize=True); mp4=work/f'seg-{i:02d}.mp4'; dur=b-a
        z="zoompan=z='min(zoom+0.00035,1.025)':x='iw/2-(iw/zoom/2)+3*sin(on/13)':y='ih/2-(ih/zoom/2)+3*cos(on/17)':d=1:s=720x1280:fps=30,format=yuv420p"
        subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-loop','1','-framerate','30','-t',f'{dur:.3f}','-i',str(img),'-vf',z,'-an','-c:v','libx264','-preset','ultrafast','-crf','18','-movflags','+faststart',str(mp4)],check=True)
        items.append((mp4,dur,t))
    concat=work/'concat.txt'; concat.write_text(''.join(f"file '{p.as_posix()}'\n" for p,_,_ in items),encoding='utf-8'); visual=work/'visual.mp4'
    subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy',str(visual)],check=True)
    subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-i',str(visual),'-i',str(ref),'-map','0:v:0','-map','1:a:0?','-c:v','copy','-c:a','aac','-b:a','160k','-shortest','-movflags','+faststart',str(out)],check=True)
    if not out.exists() or out.stat().st_size < 500000: raise SystemExit('render output missing or too small')
    meta={'status':'success','reference':str(ref),'output':str(out),'duration_sec':DUR,'fps':30,'canvas':'720x1280','visuals':'rebuilt from generated UI/assets; source visuals not reused','audio':'reference audio muxed for timing fidelity','method':'asset-based generated stills + FFmpeg motion/concat','segment_count':len(items),'phases':[{'start':0,'end':10,'name':'problem / banned accounts monitor'},{'start':10,'end':20,'name':'SocksNode proxy UI demo'},{'start':20,'end':DUR,'name':'logo + CTA outro'}],'captions':caps,'bytes':out.stat().st_size}
    analysis.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(meta,ensure_ascii=False))
finally:
    shutil.rmtree(work,ignore_errors=True)
