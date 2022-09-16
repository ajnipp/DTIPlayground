import matplotlib.pyplot as plt
import numpy
import os
import SimpleITK as sitk
import yaml

from dipy.tracking.benchmarks.bench_streamline import length
from dipy.core.gradients import gradient_table
from dipy.data import load_nifti, get_sphere, default_sphere
from dipy.direction import peaks_from_model
from dipy.io.gradients import read_bvals_bvecs
from dipy.io.stateful_tractogram import Space, StatefulTractogram
from dipy.io.streamline import save_vtk
from dipy.reconst import dti
from dipy.reconst.shm import CsaOdfModel, OpdtModel
from dipy.segment.mask import median_otsu
from dipy.tracking import utils
from dipy.tracking.local_tracking import LocalTracking 
from dipy.tracking.stopping_criterion import ThresholdStoppingCriterion
from dipy.tracking.streamline import Streamlines
from dipy.io.vtk import save_vtk_streamlines, load_vtk_streamlines

from pathlib import Path

import dtiplayground.dmri.preprocessing as prep
import dtiplayground.dmri.common as common
import dtiplayground.dmri.common.tools as tools 

logger=common.logger.write
color = common.Color

class BRAIN_Tractography_v2(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)
        
    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    def process(self,*args,**kwargs): ## variables : self.config_dir, self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        # << TODOS>>
        # create nifti files in output_dir

## old
        input_dwi = Path(self.output_dir).joinpath('input.nii.gz').__str__()
        self.writeImageWithOriginalSpace(input_dwi,'nifti',dtype='float')
        input_bval = input_dwi.replace('.nii.gz', '.bval')
        input_bvec = input_dwi.replace('.nii.gz', '.bvec')

        import nibabel as nib
        img = nib.load(input_dwi)
        # # load files
        # data, affine, img = load_nifti(input_dwi, return_img=True)
        # bvals, bvecs = read_bvals_bvecs(input_bval, input_bvec)
        # gradient_tab = gradient_table(bvals, bvecs)
## old ends
## new code
        data = self.image.images
        affine = self.image.getAffineMatrixForNifti()
        # affine=img.affine
        bvecs = [x['nifti_gradient'] for x in self.image.getGradients()]
        bvals = [x['b_value'] for x in self.image.getGradients()]
        gradient_tab = gradient_table(bvals,bvecs)

## new code ends

        # get brain mask
        masked_data, brainmask = median_otsu(data, vol_idx=[0], numpass=1)
        if self.protocol['referenceTractFile'] is not None:
            logger("Partial tractography mode",color.INFO)
            dilated_mask = self.RegisterSingleTract(**self.protocol)
            brainmask = brainmask * dilated_mask
        else:
            logger("No reference tracts are set, whole brain tractography mode is set",color.INFO)
        # get FA
        
        dti_model = dti.TensorModel(gradient_tab)
        dti_fit = dti_model.fit(masked_data, mask=brainmask)
        fa = dti_fit.fa

        # get WM mask
        if self.protocol['whiteMatterMaskThreshold'] == 'manual':
            WM_mask = self.GetWMMaskManualThreshold(fa)
        #if self.protocol['whiteMatterMaskThreshold'] == 'otsu':
        #    WM_mask = self.GetWMMaskOtsu(fa)

        fig = plt.figure()
        plt.xticks([])
        plt.yticks([])
        fig.tight_layout()
        plt.imshow(WM_mask[:, :, data.shape[2] // 2].T, cmap='gray',
                   origin='lower', interpolation='nearest')
        fig.savefig(Path(self.output_dir).joinpath('white_matter_mask.png').__str__())
        
        # generate peaks
        if self.protocol['method'] == 'tensor':
            peaks = self.GeneratePeaksTensor(masked_data, dti_model)
        elif self.protocol['method'] == 'csa':
            peaks = self.GeneratePeaksCSA(gradient_tab, masked_data)
        elif self.protocol['method'] == 'opdt':
            peaks = self.GeneratePeaksOPDT(gradient_tab, masked_data)

        logger("Method: {} was selected".format(self.protocol['method']),color.INFO)
        # generate seeds
        seeds = utils.seeds_from_mask(WM_mask, affine, density=[1, 1, 1])

        # generate tracts
        logger("Generating streamlines ...",color.PROCESS)
        stopping_criterion = ThresholdStoppingCriterion(fa, self.protocol['stoppingCriterionThreshold'])
        streamlines_generator = LocalTracking(peaks, stopping_criterion, seeds, affine=affine, step_size=.3)
        streamlines = Streamlines(streamlines_generator)
        logger("Streamlines generated.",color.OK)
        # filter tracts
        if self.protocol['removeShortTracts'] == True:
            streamlines = self.RemoveShortTracts(streamlines, self.protocol['shortTractsThreshold'])
        if self.protocol['removeLongTracts'] == True:
            streamlines = self.RemoveLongTracts(streamlines, self.protocol['longTractsThreshold'])

        # save tracts
        # sft = StatefulTractogram(streamlines, img, Space.RASMM)
        sft = StatefulTractogram(streamlines, img, Space.VOXMM)
        tract_path = Path(self.output_dir).joinpath('tractogram.vtk').__str__()
        # save_vtk(sft, tract_path, bbox_valid_check=False)
        save_vtk_streamlines(streamlines, tract_path, to_lps=False, binary=True)

        self.addOutputFile(tract_path, "tractogram")
        self.result['output']['success']=True
        return self.result
    @common.measure_time
    def GetWMMaskManualThreshold(self, fa):
        WM1 = fa > self.protocol['thresholdLow']
        WM2 = fa < self.protocol['thresholdUp']
        WM_mask_array = numpy.logical_and(WM1, WM2)
        WM_mask_array = WM_mask_array.astype(int)
        WM_mask_image = sitk.GetImageFromArray(WM_mask_array)
        WM_mask_array = self.MorphologicalOpeningWMMask(WM_mask_image)
        return WM_mask_array

    @common.measure_time
    def GetWMMaskOtsu(self, fa):
        otsu_filter = sitk.OtsuMultipleThresholdsImageFilter()
        otsu_filter.SetNumberOfThresholds(3)
        fa_image = sitk.GetImageFromArray(fa)
        WM_mask_image = otsu_filter.Execute(fa_image)
        (t1, t2, t3)= otsu_filter.GetThresholds()
        WM_mask_array = self.MorphologicalOpeningWMMask(WM_mask_image)
        WM_mask_array = WM_mask_array >= 3
        return WM_mask_array

    @common.measure_time
    def MorphologicalOpeningWMMask(self, WM_mask_image):
        opening = sitk.BinaryMorphologicalOpeningImageFilter()
        opening.SetKernelType(sitk.sitkCross)
        opening.SetKernelRadius(1)
        WM_mask_image = opening.Execute(WM_mask_image)
        WM_mask_array = sitk.GetArrayFromImage(WM_mask_image)
        return WM_mask_array

    @common.measure_time
    def GeneratePeaksTensor(self, masked_data, dti_model):
        sphere = get_sphere('symmetric362')
        peaks = peaks_from_model(model=dti_model,
            data=masked_data,
            sphere=sphere,
            relative_peak_threshold=self.protocol['relativePeakThreshold'],
            min_separation_angle=self.protocol['minPeakSeparationAngle'],
            npeaks=2)
        return peaks

    @common.measure_time
    def GeneratePeaksCSA(self, gtab, masked_data):
        csa_model = CsaOdfModel(gtab, sh_order=2)#self.protocol['shOrder'])
        peaks = peaks_from_model(model=csa_model,
            data=masked_data,
            sphere=default_sphere,
            relative_peak_threshold=self.protocol['relativePeakThreshold'],
            min_separation_angle=self.protocol['minPeakSeparationAngle'])
        return peaks

    @common.measure_time
    def GeneratePeaksOPDT(self, gtab, masked_data):
        opdt_model = OpdtModel(gtab, sh_order=2)#self.protocol['shOrder'])
        peaks = peaks_from_model(opdt_model, 
            data=masked_data,
            sphere=default_sphere,
            relative_peak_threshold=self.protocol['relativePeakThreshold'],
            min_separation_angle=self.protocol['minPeakSeparationAngle'])
        return peaks

    @common.measure_time
    def RemoveShortTracts(self, streamlines, threshold):
        streamlines_length = length(streamlines)
        number_of_streamlines = len(streamlines_length)
        long_streamlines = [streamlines[i] for i in range(number_of_streamlines) if streamlines_length[i] > threshold]
        return long_streamlines
    
    @common.measure_time
    def RemoveLongTracts(self, streamlines, threshold):
        streamlines_length = length(streamlines)
        number_of_streamlines = len(streamlines_length)
        short_streamlines = [streamlines[i] for i in range(number_of_streamlines) if streamlines_length[i] < threshold]
        return short_streamlines

## single tract registration

    @common.measure_time
    def RegisterSingleTract(self, **protocol):
        res = {}
        inputDTI = Path(self.output_dir).joinpath('input.nrrd').__str__()
        if 'dti_path' in self.global_variables:
            inputDTI = self.global_variables['dti_path']
        else:
            self.writeImageWithOriginalSpace(inputDTI,'nrrd',dtype='float')
        inputFiberFile = protocol['referenceTractFile']
        displacementField = protocol['displacementFieldFile']
        if not displacementField:
            displacementField = self.global_variables['displacement_field_path']
            if not Path(self.global_variables['displacement_field_path']).exists():
                raise Exception("Couldn't find the displacement field file")

        outputFiberTract = Path(self.output_dir).joinpath('registered_ref_tract.vtk').__str__()
        
    # Register reference tract with the displacement field 
        niralutils = tools.NIRALUtilities(softwares=self.softwares)
        niralutils.dev_mode=True
        # arguments = ['--polydata_input', inputFiberFile,
        #              '-o', outputFiberTract,
        #              '-D', displacementField,
        #              '--inverty',
        #              '--invertx']
        arguments = ['--polydata_input', inputFiberFile,
                     '-o', outputFiberTract,
                     '-D', displacementField,
                     '--inverty',
                     '--invertx']
        if self.overwriteFile(outputFiberTract) : output=niralutils.polydatatransform(arguments)
        self.addGlobalVariable('reference_tract_path', outputFiberTract) ## update tract path to the updated one

    ## Dilation and voxelization of the mapped reference tracts , getting labelmap
        labelMapFile = Path(self.output_dir).joinpath('labelmap.nrrd').__str__()
        arguments = ['--voxelize', labelMapFile,
                     '--fiber_file', outputFiberTract,
                     '-T', inputDTI]
        fiberprocess = tools.FiberProcess(softwares=self.softwares)
        fiberprocess.dev_mode = True
        if self.overwriteFile(labelMapFile) : fiberprocess.execute(arguments=arguments)
        self.addGlobalVariable('labelmap_path', labelMapFile)

    ## Dilation and voxelization of the reference tracts
        dilatedLabelmapFile = Path(self.output_dir).joinpath('labelmap_dilated.nrrd').__str__()
        dilationRadius = self.protocol['dilationRadius']
        imagemath = tools.ImageMath(softwares=self.softwares)
        imagemath.dev_mode=True
        arguments = [labelMapFile,
                     '-dilate', str(dilationRadius)+',1',
                     '-outfile', dilatedLabelmapFile
                     ]
        if self.overwriteFile(dilatedLabelmapFile) : imagemath.execute(arguments=arguments)
        self.addGlobalVariable('labelmap_path', dilatedLabelmapFile)
        labelMapImage = common.dwi.DWI(labelMapFile)
        dilatedLabelmapImage = common.dwi.DWI(dilatedLabelmapFile)
        dipyLabelMap = labelMapImage.images + dilatedLabelmapImage.images

        return dipyLabelMap

