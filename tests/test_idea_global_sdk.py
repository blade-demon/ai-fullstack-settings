import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]

class GlobalSDKTests(unittest.TestCase):
    def test_global_registration_does_not_require_or_modify_project(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary).resolve(); support=base/'support'; home=base/'home'; home.mkdir()
            shutil.copytree(ROOT/'dev-kit/.support',support)
            jdk=home/'jdk8'
            for name in ('bin','jre/lib','lib'): (jdk/name).mkdir(parents=True,exist_ok=True)
            for name,banner in [('java','openjdk version "1.8.0_432"'),('javac','javac 1.8.0_432')]:
                f=jdk/'bin'/name;f.write_text("#!/bin/sh\nprintf '%s\\n' '"+banner+"'\n");f.chmod(0o755)
            (jdk/'jre/lib/rt.jar').write_text('jar');(jdk/'lib/tools.jar').write_text('jar')
            bin_dir=base/'bin';bin_dir.mkdir();ps=bin_dir/'ps';ps.write_text('#!/bin/sh\nexit 0\n');ps.chmod(0o755)
            config=home/'idea'; table=config/'options/jdk.table.xml'
            env={'HOME':str(home),'PATH':str(bin_dir)+':/usr/bin:/bin:/usr/sbin:/sbin',
                 'JAVA_HOME':str(jdk),'JAVA_8_HOME':str(jdk),'ENV_FILE':str(home/'env.sh'),'LC_ALL':'C.UTF-8','JDK_AUTO_DETECT':'false','JDK_INSTALL_DIR':str(jdk),'IDEA_CONFIG_DIR':str(config)}
            command=['/bin/bash',str(support/'scripts/runtime/config-idea-sdk.sh'),'--global']
            first=subprocess.run(command,env=env,text=True,errors="backslashreplace",capture_output=True,timeout=15)
            self.assertEqual(first.returncode,0,first.stdout+first.stderr)
            self.assertEqual(first.stderr,"",first.stderr)
            self.assertEqual(ET.parse(table).find('.//jdk/homePath').get('value'),str(jdk))
            before=table.read_bytes()
            second=subprocess.run(command,env=env,text=True,errors="backslashreplace",capture_output=True,timeout=15)
            self.assertEqual(second.returncode,0,second.stdout+second.stderr)
            self.assertEqual(table.read_bytes(),before)
            self.assertEqual(len(ET.parse(table).findall('.//jdk')),1)

if __name__=='__main__': unittest.main()
