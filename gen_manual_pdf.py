#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import math, sys, os
sys.stdout.reconfigure(encoding='utf-8')

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable,"-m","pip","install","reportlab"])
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

W, H = A4

def draw_header_box(c, x, y, w, h, text, fontsize=10):
    c.setLineWidth(1.5)
    c.rect(x, y, w, h, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", fontsize)
    c.drawCentredString(x + w/2, y + h/2 - fontsize*0.35, text)
    c.setLineWidth(1)

def draw_bore_gauge_overview(c, x, y):
    c.saveState(); c.translate(x, y); c.setLineWidth(0.8)
    # Main bar
    c.roundRect(0, 18, 110, 8, 3, stroke=1, fill=0)
    # Grip (textured)
    c.setFillGray(0.82); c.rect(35, 17, 40, 10, stroke=1, fill=1); c.setFillGray(1)
    for i in range(7): c.line(36+i*5, 17, 36+i*5, 27)
    # Joint left
    c.setFillGray(0.88); c.roundRect(-8, 15, 12, 14, 2, stroke=1, fill=1); c.setFillGray(1)
    # Screw
    c.circle(55, 22, 3, stroke=1, fill=0)
    c.line(53,22,57,22); c.line(55,20,55,24)
    # Dial indicator
    c.circle(130, 22, 16, stroke=1, fill=0)
    c.circle(130, 22, 13, stroke=1, fill=0)
    for angle in range(0,360,30):
        r=math.radians(angle)
        c.line(130+10*math.cos(r),22+10*math.sin(r),130+12*math.cos(r),22+12*math.sin(r))
    c.setLineWidth(1.2); c.line(130,22,138,27); c.setLineWidth(0.8)
    c.line(110,22,114,22)
    # Main device left
    c.setFillGray(0.8); c.roundRect(-20,16,14,12,2,stroke=1,fill=1); c.setFillGray(1)
    c.line(-20,22,-26,22); c.circle(-27,22,2,stroke=1,fill=0)
    c.line(-20,19,-24,16); c.circle(-25,15,2,stroke=1,fill=0)
    # Number labels
    c.setFont("Helvetica-Bold",7)
    for (lx,ly,t) in [(-22,10,"1"),(-3,10,"2"),(50,10,"3"),(53,32,"4"),(128,41,"5")]:
        c.drawCentredString(lx,ly,t)
    c.restoreState()

def draw_anvil_exploded(c, x, y):
    c.saveState(); c.translate(x,y); c.setLineWidth(0.8)
    c.setFillGray(0.7); c.roundRect(-8,70,16,10,2,stroke=1,fill=1); c.setFillGray(1)
    c.setFont("Helvetica",5.5); c.drawString(10,74,"6-Piulita blocare")
    c.setFillGray(0.82); c.roundRect(-5,54,10,12,1,stroke=1,fill=1); c.setFillGray(1)
    c.drawString(10,59,"7-Nicovala")
    c.ellipse(-7,43,7,49,stroke=1,fill=0); c.drawString(10,45,"8-Saiba")
    c.setFillGray(0.78); c.roundRect(-10,15,20,26,3,stroke=1,fill=1); c.setFillGray(1)
    c.line(-8,25,-8,35); c.line(8,25,8,35)
    c.drawString(12,28,"9-Ghidaj")
    c.circle(0,8,5,stroke=1,fill=0); c.circle(0,8,2,stroke=1,fill=1)
    c.drawString(8,6,"10-Punct contact")
    c.setDash(2,2); c.line(0,82,0,0); c.setDash()
    c.restoreState()

def draw_attaching(c, x, y):
    c.saveState(); c.translate(x,y); c.setLineWidth(0.8)
    c.circle(20,30,20,stroke=1,fill=0); c.circle(20,30,17,stroke=1,fill=0)
    for a in range(0,360,36):
        r=math.radians(a)
        c.line(20+14*math.cos(r),30+14*math.sin(r),20+16*math.cos(r),30+16*math.sin(r))
    c.setLineWidth(1.2); c.line(20,30,28,35); c.setLineWidth(0.8)
    c.setFillGray(0.82); c.roundRect(12,-8,16,14,2,stroke=1,fill=1); c.setFillGray(1)
    c.setLineWidth(1.2); c.line(20,10,20,-8); c.line(17,-5,20,-9); c.line(23,-5,20,-9); c.setLineWidth(0.8)
    c.setFont("Helvetica",6.5); c.drawString(24,-3,"1,6 mm")
    c.setFillGray(0.6); c.roundRect(35,8,16,8,2,stroke=1,fill=1); c.setFillGray(1)
    c.setFont("Helvetica",6); c.drawString(37,10,"surub")
    c.restoreState()

def draw_anvil_sel(c, x, y):
    c.saveState(); c.translate(x,y); c.setLineWidth(0.8)
    c.setFillGray(0.9); c.rect(0,22,44,28,stroke=1,fill=1); c.setFillGray(1)
    for i,w in enumerate([5,10,18,25]):
        c.setFillGray(0.5); c.rect(4+i*9,28,6,w,stroke=1,fill=1); c.setFillGray(1)
    c.setFont("Helvetica-Bold",12); c.drawString(46,32,"+")
    c.setFillGray(0.78); c.ellipse(56,26,72,36,stroke=1,fill=1)
    c.setFillGray(1); c.circle(64,31,3,stroke=1,fill=1)
    c.line(22,22,22,14); c.line(19,17,22,13); c.line(25,17,22,13)
    c.setFillGray(0.6); c.roundRect(12,3,22,9,2,stroke=1,fill=1); c.setFillGray(1)
    for i in range(4): c.line(14+i*5,3,14+i*5,12)
    c.setFont("Helvetica",6); c.drawCentredString(23,-2,"Piulita randalinata")
    c.restoreState()

def draw_micrometer(c, x, y):
    c.saveState(); c.translate(x,y); c.setLineWidth(0.8)
    c.roundRect(0,0,62,55,5,stroke=1,fill=0)
    c.setFillGray(0.65); c.rect(43,20,20,16,stroke=1,fill=1); c.setFillGray(1)
    c.rect(14,25,29,7,stroke=1,fill=0)
    for i in range(6): c.line(16+i*4,32,16+i*4,36)
    c.line(5,28,14,28); c.circle(4,28,3,stroke=1,fill=0)
    c.line(43,28,37,28)
    c.setFillGray(0.55); c.roundRect(33,23,9,10,2,stroke=1,fill=1); c.setFillGray(1)
    c.setDash(2,2); c.circle(26,28,18,stroke=1,fill=0); c.setDash()
    c.setFont("Helvetica-Bold",7); c.drawCentredString(26,20,"Ø 50mm")
    c.setFont("Helvetica",6); c.drawCentredString(26,12,"Piulita blocare")
    c.setFont("Helvetica",7); c.drawCentredString(31,-7,"▲ Micrometru")
    c.restoreState()

def draw_zero(c, x, y):
    c.saveState(); c.translate(x,y); c.setLineWidth(0.8)
    c.setFillGray(0.88); c.roundRect(14,0,52,44,4,stroke=1,fill=1); c.setFillGray(1)
    c.line(14,21,5,21); c.circle(4,21,3,stroke=1,fill=0)
    c.line(66,21,73,21)
    c.setFillGray(0.78); c.roundRect(24,30,30,8,2,stroke=1,fill=1); c.setFillGray(1)
    c.circle(52,55,14,stroke=1,fill=0); c.circle(52,55,11,stroke=1,fill=0)
    for a in range(0,360,30):
        r=math.radians(a)
        c.line(52+9*math.cos(r),55+9*math.sin(r),52+11*math.cos(r),55+11*math.sin(r))
    c.setLineWidth(1.4); c.line(52,55,52,63); c.setLineWidth(0.8)
    c.setDash(2,2); c.circle(52,55,20,stroke=1,fill=0); c.setDash()
    c.setFont("Helvetica-Bold",10); c.drawCentredString(52,51,"0")
    c.setFont("Helvetica",9); c.drawString(34,74,"◄"); c.drawString(64,74,"►")
    c.restoreState()

def draw_pos_A(c, x, y):
    c.saveState(); c.translate(x,y); c.setLineWidth(0.8)
    c.setFillGray(0.7); c.circle(30,30,28,stroke=1,fill=1); c.setFillGray(1); c.circle(30,30,22,stroke=1,fill=1)
    c.setFillGray(0.3); c.rect(8,27,44,6,stroke=1,fill=1); c.setFillGray(1)
    c.setFillGray(0.15); c.circle(8,30,3,stroke=0,fill=1); c.circle(52,30,3,stroke=0,fill=1); c.setFillGray(1)
    c.setFont("Helvetica-Bold",8); c.drawCentredString(30,45,"A")
    c.setLineWidth(1); c.line(30,44,30,36); c.line(27,40,30,44); c.line(33,40,30,44)
    c.setFont("Helvetica-Bold",10); c.drawCentredString(30,-7,"A")
    c.restoreState()

def draw_pos_B(c, x, y):
    c.saveState(); c.translate(x,y); c.setLineWidth(0.8)
    c.setFillGray(0.7); c.rect(5,0,50,50,stroke=1,fill=1); c.setFillGray(1); c.rect(10,5,40,40,stroke=1,fill=1)
    c.setFillGray(0.3); c.rect(27,5,6,40,stroke=1,fill=1); c.setFillGray(1)
    c.setFillGray(0.15); c.circle(30,5,3,stroke=0,fill=1); c.circle(30,45,3,stroke=0,fill=1); c.setFillGray(1)
    c.setFont("Helvetica-Bold",8); c.drawString(13,27,"B")
    c.line(14,26,27,26); c.line(22,23,27,26); c.line(22,29,27,26)
    c.setFont("Helvetica-Bold",10); c.drawCentredString(30,-7,"B")
    c.restoreState()

def draw_multi(c, x, y):
    c.saveState(); c.translate(x,y); c.setLineWidth(0.7)
    c.setFillGray(0.72); c.circle(28,28,26,stroke=1,fill=1); c.setFillGray(1); c.circle(28,28,20,stroke=1,fill=1)
    c.setDash(3,2); c.line(28,2,28,54); c.line(2,28,54,28); c.setDash()
    c.setFont("Helvetica",7); c.drawString(30,34,"A-1"); c.drawString(30,20,"A-2")
    c.rect(62,5,38,46,stroke=1,fill=0)
    c.setDash(2,2); c.line(62,20,100,20); c.line(62,30,100,30); c.line(62,40,100,40); c.setDash()
    c.setFont("Helvetica",7)
    c.drawString(64,42,"B-1"); c.drawString(74,32,"B-2"); c.drawString(74,22,"B-3")
    c.restoreState()

def draw_rot_top(c, x, y):
    c.saveState(); c.translate(x,y); c.setLineWidth(0.8)
    c.circle(30,30,28,stroke=1,fill=0); c.circle(30,30,8,stroke=1,fill=0)
    for a in [0,90,180,270]:
        r=math.radians(a); x1=30+10*math.cos(r); y1=30+10*math.sin(r)
        x2=30+22*math.cos(r); y2=30+22*math.sin(r); c.line(x1,y1,x2,y2)
        p=math.radians(a+90)
        c.line(x2,y2,x2-3*math.cos(r)+2*math.cos(p),y2-3*math.sin(r)+2*math.sin(p))
        c.line(x2,y2,x2-3*math.cos(r)-2*math.cos(p),y2-3*math.sin(r)-2*math.sin(p))
    c.setFont("Helvetica",10); c.drawString(0,28,"↺"); c.drawString(52,28,"↻")
    c.restoreState()

def draw_rot_side(c, x, y):
    c.saveState(); c.translate(x,y); c.setLineWidth(0.8)
    c.setFillGray(0.65); c.rect(0,40,65,12,stroke=1,fill=1); c.rect(0,0,65,12,stroke=1,fill=1); c.setFillGray(1)
    c.setFillGray(0.82); c.roundRect(22,12,20,28,3,stroke=1,fill=1); c.setFillGray(1)
    c.circle(32,12,4,stroke=1,fill=0); c.circle(32,40,4,stroke=1,fill=0)
    c.setFont("Helvetica",11); c.drawString(2,23,"←"); c.drawString(53,23,"→")
    c.setDash(2,2); c.arc(10,10,54,42,70,40); c.setDash()
    c.restoreState()

def page1(c):
    margin=20*mm
    c.setFillGray(0)
    c.rect(margin, H-30*mm, W-2*margin, 16*mm, stroke=0, fill=1)
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold",16)
    c.drawCentredString(W/2, H-22*mm, "MANUAL DE UTILIZARE")
    c.setFillColor(colors.black)
    c.setFont("Helvetica",8); c.drawCentredString(W/2, H-27*mm, "Comparator de Alezaj")

    y=H-36*mm
    draw_header_box(c,margin,y-7*mm,W-2*margin,7*mm,"DENUMIRE SI CONSTRUCTIE",10)
    y-=7*mm
    draw_bore_gauge_overview(c,margin+5,y-42*mm)
    c.setFont("Helvetica-Bold",8); c.drawString(W/2+5,y-8*mm,"Componente fata:")
    for i,(num,name) in enumerate([("1","Dispozitiv principal"),("2","Imbinare (joint)"),
            ("3","Maner (grip)"),("4","Surub"),("5","Comparator cu cadran")]):
        c.setFont("Helvetica",7.5); c.drawString(W/2+5,y-14*mm-i*5*mm,f"  ({num})  {name}")
    c.setFont("Helvetica-Bold",8); c.drawString(W/2+5,y-42*mm,"Componente cap masurare:")
    for i,(num,name) in enumerate([("6","Piulita blocare nicovala"),("7","Nicovala/componente"),
            ("8","Saiba"),("9","Dispozitiv de ghidare"),("10","Punct de contact")]):
        c.setFont("Helvetica",7.5); c.drawString(W/2+5,y-48*mm-i*5*mm,f"  ({num})  {name}")
    draw_anvil_exploded(c,W/2+50*mm,y-70*mm)

    y=H-100*mm
    draw_header_box(c,margin,y-7*mm,W-2*margin,7*mm,"ASAMBLARE",10); y-=7*mm
    c.setFont("Helvetica-Bold",8); c.drawString(margin+2,y-5*mm,"(1) Montarea comparatorului")
    draw_attaching(c,margin+5,y-60*mm)
    for i,t in enumerate(["● Introduceti tija comparatorului in imbinare.",
            "● Tija patrunde aproximativ 1,6 mm.","● Acul face ~o rotatie completa.",
            "● Blocati comparatorul cu surubul."]):
        c.setFont("Helvetica",7.5); c.drawString(margin+55,y-15*mm-i*5*mm,t)
    c.setFont("Helvetica-Bold",8); c.drawString(W/2+5,y-5*mm,"(2) Selectarea nicovalelor / saibelor")
    draw_anvil_sel(c,W/2+8,y-62*mm)
    for i,t in enumerate(["● Scoateti piulita si nicovalele neutilizate.",
            "● Instalati nicovalele/saibele corecte.","■ Selectati numarul MINIM.",
            "● Insurubati bine piulita randalinata."]):
        c.setFont("Helvetica",7.5); c.drawString(W/2+80,y-15*mm-i*5*mm,t)

    y=H-180*mm
    draw_header_box(c,margin,y-7*mm,W-2*margin,7*mm,"SETAREA DIMENSIUNII",10); y-=7*mm
    c.setFont("Helvetica-Bold",8); c.drawString(margin+2,y-5*mm,"(1) Reglati micrometrul la dimensiunea exacta de masurat.")
    draw_micrometer(c,margin+10,y-68*mm)
    for i,t in enumerate(["■ Exemplu: Ø 50 mm","■ Blocati piulita dupa setare.",
            "■ Consultati instructiunile micrometrului."]):
        c.setFont("Helvetica",7.5); c.drawString(margin+78,y-20*mm-i*5*mm,t)
    c.setFont("Helvetica-Bold",8); c.drawString(W/2+5,y-5*mm,"(2) Aduceti acul comparatorului la zero.")
    draw_zero(c,W/2+25,y-75*mm)
    for i,t in enumerate(["● Plasati contactele pe fetele micrometrului.",
            "● Ajustati pana la pozitia MAX.","■ Rotiti cadranul pentru a aduce","   acul exact la 0."]):
        c.setFont("Helvetica",7.5); c.drawString(W/2+5,y-20*mm-i*5*mm,t)

    c.setFont("Helvetica",7); c.setFillGray(0.5)
    c.drawCentredString(W/2,12*mm,"Pagina 1 din 2  |  Manual Comparator de Alezaj")
    c.setFillGray(0); c.showPage()

def page2(c):
    margin=20*mm
    y=H-15*mm
    draw_header_box(c,margin,y-7*mm,W-2*margin,7*mm,"METODE DE MASURARE SI CITIRE",10); y-=7*mm

    draw_pos_A(c,margin+5,y-70*mm)
    c.setFont("Helvetica-Bold",8); c.drawString(margin+2,y-5*mm,"Pozitia A - Sectiune transversala:")
    for i,t in enumerate(["● La pozitia A, acul comparatorului","   indica valoarea MINIMA.",
            "   Acesta este punctul corect de masurare.","■ Rotiti comparatorul ca in figura","   din dreapta pentru a gasi poz. A."]):
        c.setFont("Helvetica",7.5); c.drawString(margin+65,y-12*mm-i*5*mm,t)
    draw_rot_top(c,W/2+30*mm,y-68*mm)

    y-=75*mm
    draw_pos_B(c,margin+5,y-65*mm)
    c.setFont("Helvetica-Bold",8); c.drawString(margin+2,y-5*mm,"Pozitia B - Sectiune verticala:")
    for i,t in enumerate(["● La pozitia B, acul comparatorului","   indica valoarea MINIMA.",
            "   Acesta este punctul corect de masurare.","■ Rotiti comparatorul ca in figura","   din dreapta pentru a gasi poz. B."]):
        c.setFont("Helvetica",7.5); c.drawString(margin+65,y-12*mm-i*5*mm,t)
    draw_rot_side(c,W/2+25*mm,y-62*mm)

    y-=75*mm
    draw_multi(c,margin+5,y-55*mm)
    c.setFont("Helvetica-Bold",8); c.drawString(margin+2,y-5*mm,"Masurare in mai multe pozitii:")
    for i,t in enumerate(["■ Pentru date exacte, masurati in","   MAI MULTE pozitii (A-1, A-2","   si B-1, B-2, B-3) conform","   figurilor din stanga."]):
        c.setFont("Helvetica",7.5); c.drawString(margin+115,y-12*mm-i*5*mm,t)

    y-=68*mm
    draw_header_box(c,margin,y-7*mm,W-2*margin,7*mm,"SPECIFICATII",10); y-=7*mm
    cols=[48*mm,42*mm,25*mm,25*mm,32*mm]
    heads=["Domeniu masurare","Adancime masurare","Nicovale","Saibe","Componente"]
    rows=[["18-35 mm","150 mm","7","-","-"],["35-50 mm","150 mm","4","4","-"],
          ["50-100 mm","150 mm","11","4","-"],["50-160 mm","150 mm","12","4","1"]]
    rh=7*mm; tx=margin; ty=y-rh
    c.setFillGray(0.18); c.rect(tx,ty,sum(cols),rh,stroke=1,fill=1)
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold",7.5)
    cx=tx
    for i,h in enumerate(heads): c.drawCentredString(cx+cols[i]/2,ty+2*mm,h); cx+=cols[i]
    c.setFillColor(colors.black)
    for ri,row in enumerate(rows):
        ry=ty-(ri+1)*rh
        c.setFillGray(0.93 if ri%2==0 else 1.0); c.rect(tx,ry,sum(cols),rh,stroke=1,fill=1); c.setFillColor(colors.black)
        cx=tx
        for i,cell in enumerate(row): c.setFont("Helvetica",7.5); c.drawCentredString(cx+cols[i]/2,ry+2*mm,cell); cx+=cols[i]

    y-=(len(rows)+1)*rh+10*mm
    draw_header_box(c,margin,y-7*mm,W-2*margin,7*mm,"ATENTIE",10); y-=7*mm
    cautions=["Nu dezasamblati si nu modificati aparatul de masurare.",
              "Nu supuneti aparatul la lovituri sau socuri mecanice.",
              "Curatati si aplicati strat anticoroziv dupa utilizare. Dezasamblati\n   comparatorul (poate afecta precizia). Depozitati in cutie.",
              "Nu inlocuiti nicovalele, saibele etc. cu altele necorespunzatoare."]
    ty2=y-10*mm
    for t in cautions:
        c.setFont("Helvetica-Bold",8); c.drawString(margin+2,ty2,"■")
        c.setFont("Helvetica",8)
        for line in t.split('\n'): c.drawString(margin+9,ty2,line); ty2-=5*mm
        ty2-=2*mm

    c.setFont("Helvetica",7); c.setFillGray(0.5)
    c.drawCentredString(W/2,12*mm,"Pagina 2 din 2  |  Manual Comparator de Alezaj")
    c.setFillGray(0); c.showPage()

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "manual_comparator_alezaj_RO.pdf")
cv = canvas.Canvas(OUT, pagesize=A4)
cv.setTitle("Manual Comparator de Alezaj - Romana")
page1(cv); page2(cv); cv.save()
print("PDF generat:", OUT)
input("Apasa Enter pentru a inchide...")
