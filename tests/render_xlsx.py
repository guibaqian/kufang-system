"""比对用：把下载的 xlsx 用 LibreOffice 转成 PDF → PNG。LibreOffice 不认原表的「不显示 0」（showZeros=0），
所以只在这份渲染副本里给所有格子套数字格式 0;-0;;@（0 显示成空），原文件不动。用法：render_xlsx.py in.xlsx out.png"""
import sys, re, zipfile, subprocess, tempfile, os, shutil
src, png = sys.argv[1], sys.argv[2]; tmp = tempfile.mkdtemp(); cp = os.path.join(tmp, 'r.xlsx')
zi = zipfile.ZipFile(src); zo = zipfile.ZipFile(cp, 'w', zipfile.ZIP_DEFLATED)
for n in zi.namelist():
    d = zi.read(n)
    if n == 'xl/styles.xml':
        s = d.decode(); nf = '<numFmt numFmtId="200" formatCode="0;-0;;@"/>'
        if '<numFmts' in s: s = re.sub(r'<numFmts count="(\d+)">', lambda m: '<numFmts count="%d">%s' % (int(m.group(1)) + 1, nf), s)
        else: s = s.replace('<fonts', '<numFmts count="1">%s</numFmts><fonts' % nf, 1)
        a, b = s.split('<cellXfs', 1); b1, b2 = b.split('</cellXfs>', 1)
        fix = lambda m: '<xf ' + re.sub(r'\s*(numFmtId|applyNumberFormat)="\d+"', '', m.group(1)) + ' numFmtId="200" applyNumberFormat="1"'
        b1 = re.sub(r'<xf ([^>]*?)(?=/?>)', fix, b1); d = (a + '<cellXfs' + b1 + '</cellXfs>' + b2).encode()
    zo.writestr(n, d)
zo.close()
subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', '--outdir', tmp, cp], capture_output=True, timeout=120)
print(subprocess.run(['pdfinfo', os.path.join(tmp, 'r.pdf')], capture_output=True, text=True).stdout.count('Pages:'))
subprocess.run(['pdftoppm', '-r', '110', '-png', '-singlefile', os.path.join(tmp, 'r.pdf'), png[:-4]]); shutil.rmtree(tmp)
