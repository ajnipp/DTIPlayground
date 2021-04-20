
from dtiprep.modules import DTIPrepModule
import dtiprep,yaml
import DIFFUSION_Check.testmodule as tm 

logger=dtiprep.logger.write 

class DIFFUSION_Check(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(DIFFUSION_Check)

    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    def process(self): ### variables : self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        logger("NOT IMPLEMENTED YET",dtiprep.Color.ERROR)


        return self.result


