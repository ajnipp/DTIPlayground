#!/usr/bin/python3

from pathlib import Path
import dtiprep
from dtiprep.dwi import DWI 
import dtiprep.modules
import dtiprep.protocols as protocols
import numpy as np 
import argparse,yaml
import traceback
import time 
import copy
import yaml
import dtifa #dti fiber analyser
import dtiab #dti atlas builder

logger=dtiprep.logger.write

def io_test():
    
    try:
        fname_nrrd="_data/images/CT-00006_DWI_dir79_APPA.nrrd"
        # fname_nifti="data/images/CT-00006_DWI_dir79_APPA.nii.gz"
        # dwi_nifti=DWI(fname_nifti)
        dwi_nrrd=DWI(fname_nrrd)
        logger(str(dwi_nrrd.information))

        # err=0.0
        # for g in zip(dwi_nifti,dwi_nrrd):
        #     dnifti,dnrrd=g
        #     img_nrrd, grad_nrrd = dnrrd
        #     img_nifti,grad_nifti= dnifti
        #     err+= np.sum((grad_nifti['b_value']-grad_nrrd['b_value'])**2)

        bt=time.time()
        newdwi=copy.deepcopy(dwi_nrrd)
        refdwi=dwi_nrrd
        elapsed=time.time()-bt
        logger("Elapsed time to copy image : {}s".format(elapsed))

        newdwi.images=None
        logger(str(dwi_nrrd.images[:,:,40,0]))
        logger(str(newdwi.images))
        logger("Original address : "+str(dwi_nrrd))
        logger("Deepcopied address : "+str(newdwi))
        logger("Referenced address : "+str(refdwi))
        
        
        dwi_nrrd.setB0Threshold(b0_threshold=1500)
        # grad_with_baselines=dwi_nrrd.getGradients()
        # for g in grad_with_baselines:
        #     if g['baseline']:
        #         logger(str(g['b_value']))
        ### writing
        #dwi_nrrd.writeImage('test.nrrd')
        return True
    except Exception as e:
        logger("Exception occurred : {}".format(str(e)))
        traceback.print_exc()
        return False
    
def protocol_test():
    try:
        fname_nrrd="_data/images/CT-00006_DWI_dir79_APPA.nrrd"
        #fname_nrrd="_data/images/MMU45938_DTI_HF_fix1.nrrd"
        #fname_nrrd="_data/images/neo-0378-1-1-10year-DWI_dir79_AP_1-series.nrrd"
        #fname_nrrd="_data/images/ImageTest1.nrrd"
        output_dir=str(Path(fname_nrrd).parent.joinpath("output"))
        logfile=str(Path(output_dir).joinpath('log.txt'))
        Path(output_dir).mkdir(parents=True,exist_ok=True)
        dtiprep.logger.setLogfile(logfile)
        pipeline=['DIFFUSION_Check','SLICE_Check','INTERLACE_Check']#,'EDDYMOTION_Correct']
        modules=dtiprep.modules.load_modules(user_module_paths=['user/modules'])
        proto=protocols.Protocols(modules)
        #proto.loadProtocols("data/protocol_files/protocols.yml")
        proto.setImagePath(fname_nrrd)
        proto.setOutputDirectory(output_dir)
        proto.makeDefaultProtocols(pipeline=pipeline)
        #proto.addPipeline('TEST_Check',index=13,default_protocol=False)
        res=proto.runPipeline()
        #logger(yaml.dump(res))
        #proto.writeProtocols(Path(output_dir).joinpath("protocols.yml").__str__())
        #logger(yaml.dump(proto.modules))
        return res
    except Exception as e:
        logger("Exception occurred : {}".format(str(e)))
        traceback.print_exc()
        return False
    pass
    
def run_tests(testlist: list):
    for idx,t in enumerate(testlist):
        logger("---------------------------------------")
        logger("--------- {}/{} - Running : {}".format(idx+1,len(testlist),t))
        logger("---------------------------------------")
        if eval(t)() : logger("[{}/{}] : {} - Success".format(idx+1,len(testlist),t))
        else: logger("[{}/{}] : {} - Failed".format(idx+1,len(testlist),t))

if __name__=='__main__':
    current_dir=Path(__file__).parent
    parser=argparse.ArgumentParser()
    parser.add_argument('--log',help='log file',default=str(current_dir.joinpath('_data/log.txt')))
    args=parser.parse_args()
    dtiprep.logger.setLogfile(args.log)
    dtiprep.logger.setTimestamp(False)
    
    tests=['io_test','protocol_test']
    run_tests(tests[1:])