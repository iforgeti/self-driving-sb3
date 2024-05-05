# Load model directly
from transformers import SegformerImageProcessor, SegformerForSemanticSegmentation,AutoImageProcessor,Mask2FormerForUniversalSegmentation
import numpy as np
from PIL import Image
import torch
from torch import nn
import cv2
import colorsys


class SegmodelWrapper():

    """
    requirement for this class

    init
    self.default_numlabels:
    have to use apply_label_mapping(label_mapping,custom_palette) after init materials for predict method
        
        
    method:

        warmup(self,image_shape=(512,1024,3)) : do inference and print the avg time
        generate_colors(num_classes) : generate color for labels
        apply_label_mapping(self,label_mapping,custom_palette = None): it apply the label mapping for post process 
        predict(self,images): have to imprement
        convert_label(self,seg_maps): for convert original semantic map to desired semantic map base on label_mapping
        get_seg_overlay(self,images, segs,original_size = True): get the image overlay results

    """

   
    def __init__(self):        

        self.device  = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print("using ",self.device)


    def warmup(self,image_shape=(512,1024,3),batch=1):
        # warmup
        dummpy_images = [np.random.randint(0, 255, image_shape, dtype=np.uint8)]*batch
        self.predict(dummpy_images)
        st = time.time()
        for _ in range(3):
            self.predict(dummpy_images)
        print(f"inference time :{(time.time()-st)/3:.2f}")

    @staticmethod
    def generate_colors(num_classes):
        hsv_colors = [(i / num_classes, 1.0, 1.0) for i in range(num_classes)]
        rgb_colors = [colorsys.hsv_to_rgb(*color) for color in hsv_colors]
        rgb_colors = [(int(r * 255), int(g * 255), int(b * 255)) for (r, g, b) in rgb_colors]
        return np.array(rgb_colors).astype(np.uint8)
    
    def apply_label_mapping(self,label_mapping,custom_palette = None):
        
        if label_mapping is not None:
            labels = list(set(label_mapping.values()))
            assert labels == list(range(max(labels)+1))
            num_labels = len(labels)
        else:
            num_labels = self.default_numlabels
        self.label_mapping = label_mapping
        self.palette = custom_palette if custom_palette and len(custom_palette) >= num_labels \
            else self.generate_colors(num_labels)


    def predict(self,images):

        """
        inputs: list of images
        return predict output and overlayed image

        should apply for post process
        if self.label_mapping is not None:
            pred_segs = self.convert_label(pred_segs)  

        """
        raise NotImplementedError("Method 'predict' must be implemented in subclasses")
    
    def convert_label(self,seg_maps):

        new_segmaps = []

        for seg_map in seg_maps:

            postprocessed = np.full(seg_map.shape,255, dtype=np.uint8)

            for k,v in self.label_mapping.items():
                postprocessed[seg_map==k]=v

            new_segmaps.append(postprocessed)

        return new_segmaps
         
    
    def get_seg_overlay(self,images, segs,original_size = True):

        if len(images) != len(segs):
            raise ValueError("Number of images and segmentation results must be equal")
        
        imgs=[]
        for i in range(len(images)):
            color_seg = np.zeros((segs[i].shape[0], segs[i].shape[1], 3), dtype=np.uint8) # height, width, 3
            for label, color in enumerate(self.palette):
                color_seg[segs[i] == label, :] = color

            color_seg[segs[i] == 255, :] = [0,0,0]

            # Show image + mask
            if images[0].shape[:-1] != segs[0].shape:
                if original_size:
                    img = images[i] * 0.5 + cv2.resize(color_seg,(images[i].shape[1],images[i].shape[0]),interpolation= cv2.INTER_LINEAR) * 0.5
                else:
                    img = cv2.resize(images[i],(segs[i].shape[1],segs[i].shape[0])) * 0.5 + color_seg * 0.5
            else:
                img = images[i] * 0.5 + color_seg * 0.5

            imgs.append(img.astype(np.uint8))

        return imgs
    
class HF_segFormermodel(SegmodelWrapper):
   
    def __init__(self,model_repo,label_mapping=None,custom_processor=None,custom_palette=None):

        super().__init__()

        self.label_mapping = label_mapping
        self.custom_processor = custom_processor
        self.processor = custom_processor or SegformerImageProcessor.from_pretrained(model_repo)
        self.model = SegformerForSemanticSegmentation.from_pretrained(model_repo).to(self.device)
        self.default_numlabels = self.model.config.num_labels
        self.apply_label_mapping(label_mapping,custom_palette)
        self.warmup()
    
    def predict(self,images,upsampling = False):

        """
        inputs: list of images
        return predict output and overlayed image
        """

        with torch.no_grad():
            if self.custom_processor == None:
                inputs = self.processor(images,return_tensors="pt")['pixel_values'].to(self.device)
            else:
                inputs = self.processor(torch.stack([self.processor(img) for img in images],axis=0)).to(self.device)

            logits = self.model(pixel_values = inputs).logits

        if upsampling:

            logits = nn.functional.interpolate(
                logits,
                size=images[0].shape[:-1], # (height, width)
                mode='bilinear',
                align_corners=False
            )

            pred_segs = logits.argmax(dim=1).cpu()
        
        else:

            pred_segs = logits.argmax(dim=1).cpu()

        if self.label_mapping is not None:
            pred_segs = self.convert_label(pred_segs)  

        return pred_segs,logits
         
    

class HF_mask2Formermodel(SegmodelWrapper):
   
    def __init__(self,model_repo,label_mapping = None,custom_processor=None,custom_palette=None):
        super().__init__()

        if label_mapping is not None:
            assert isinstance(label_mapping,dict)

        self.custom_processor = custom_processor
        self.processor = AutoImageProcessor.from_pretrained(model_repo) if self.custom_processor is None else self.custom_processor
        self.model = Mask2FormerForUniversalSegmentation.from_pretrained(model_repo).to(self.device)
        self.default_numlabels = self.model.config.num_labels
        self.apply_label_mapping(label_mapping,custom_palette)
        self.warmup()

    def predict(self,images):

        """
        inputs: list of images
        return predict output and overlayed image
        """

        with torch.no_grad():
            if self.custom_processor == None:
                inputs = self.processor(images,return_tensors="pt")['pixel_values'].to(self.device)
            else:
                inputs = self.processor(torch.stack([self.processor(img) for img in images],axis=0)).to(self.device)

            outputs = self.model(pixel_values = inputs)

        seg_maps = self.processor.post_process_semantic_segmentation(outputs, target_sizes=[image.shape[:-1] for image in images])

        seg_maps = [seg.cpu().numpy() for seg in seg_maps]

        if self.label_mapping is not None:
            seg_maps = self.convert_label(seg_maps)

        return seg_maps,outputs
    

# tensorrt==================================================================================================
# convert the model in full-dimensions mode with an given input shape:
# /home/lpr/TensorRT-8.6.1.6/bin/trtexec \
# --onnx=fan-tiny/cityscapes_fan_tiny_hybrid_224.onnx \
# --saveEngine=fan-tiny/cityscapes_fan_tiny_hybrid_3x3x224x224_onnx_engine.trt \
# --shapes=input:3x3x224x224


import numpy as np
import os
import pycuda.driver as cuda
import pycuda.autoinit

import matplotlib.pyplot as plt
from PIL import Image

import tensorrt as trt
import os
import time



os.environ['CUDA_MODULE_LOADING'] = 'LAZY'

# Check TensorRT version
# print("TensorRT version:", trt.__version__)
# assert trt.Builder(trt.Logger())




class segFormerTRT(SegmodelWrapper):

    def __init__(self,model_path,label_mapping=None,preprocessor=None,custom_palette=None,num_classes = 20):

        # load tensorrt engine =====================
        print("TensorRT version:", trt.__version__)
        TRT_LOGGER = trt.Logger()
        engine_file_path = model_path
        assert os.path.exists(engine_file_path)
        print("Reading engine from file {}".format(engine_file_path))
        with open(engine_file_path, "rb") as f, trt.Runtime(TRT_LOGGER) as runtime:
            self.engine = runtime.deserialize_cuda_engine(f.read())

        self.input_shape = tuple(self.engine.get_tensor_shape("input"))

        self.context = self.engine.create_execution_context()
        self.context.set_input_shape("input", self.input_shape)
        assert self.context.all_binding_shapes_specified

        self.preprocessor = preprocessor if preprocessor is not None else self.preprocess

        self.default_numlabels = num_classes
        self.apply_label_mapping(label_mapping,custom_palette)
        self.warmup()
    

    def predict(self,images):
        """
        input : list of bgr image

        return : logits => numpy array (batch,h,w)
        
        """

        preprocessed_images = self.preprocessor(images)

        # Allocate host and device bufferstrt_model.engine.get_tensor_name
        bindings = []
        for binding in self.engine:
            size = trt.volume(self.context.get_tensor_shape(binding))
            dtype = trt.nptype(self.engine.get_tensor_dtype(binding))
            if binding == 'input':
                input_buffer = np.ascontiguousarray(preprocessed_images)
                input_memory = cuda.mem_alloc(preprocessed_images.nbytes)
                bindings.append(int(input_memory))
            else:
                output_buffer = cuda.pagelocked_empty(size, dtype)
                output_memory = cuda.mem_alloc(output_buffer.nbytes)
                bindings.append(int(output_memory))

        stream = cuda.Stream()
        # Transfer input data to the GPU.
        cuda.memcpy_htod_async(input_memory, input_buffer, stream)
        # Run inference
        self.context.execute_async_v2(bindings=bindings, stream_handle=stream.handle)
        # Transfer prediction output from the GPU.
        cuda.memcpy_dtoh_async(output_buffer, output_memory, stream)
        # Synchronize the stream
        stream.synchronize()

        pred_segs = np.reshape(output_buffer,(self.input_shape[0],*self.input_shape[-2:]))

        if self.label_mapping is not None:
            pred_segs = self.convert_label(pred_segs)  

        return pred_segs
        

    def preprocess(self,images):
        """
        input : list of bgr image

        return : preprocessed batch of image => numpy array (batch,ch,h,w)
        
        """

        # Resize the image to match the specified input dimensions (1024x1024)
        preprocessed_images = []

        for image in images:
            input_width, input_height = self.input_shape[-2:]
            resized_image = cv2.resize(image, (input_width, input_height))
            resized_image = cv2.cvtColor(resized_image, cv2.COLOR_BGR2RGB)

            # Convert the image to float32 and apply color format adjustment
            resized_image = resized_image.astype(np.float32)
            resized_image -= np.array([123.675, 116.28, 103.53])

            # Scale the image data by the net-scale-factor
            net_scale_factor = 0.01735207357279195
            resized_image *= net_scale_factor

            # Expand dimensions to match the model input shape (3, 1024, 1024)
            preprocessed_image = np.transpose(resized_image, (2, 0, 1))  # (H, W, C) to (C, H, W)

            # Convert the preprocessed image to a format suitable for inference (e.g., to Tensor)
            preprocessed_images.append(preprocessed_image)

        return np.stack(preprocessed_images,axis=0)
    

    def postprocess(self,datas):
        """
        input : logits data (segmentation result)

        return : pil image of semantic segmentation 

        """
        imgs = []
        for data in datas:
            img = Image.fromarray(data.astype('uint8'), mode='P')
            img.putpalette(self.palette)
            imgs.append(img)
        return imgs
    

    



# class segFormerTRT_v10():

#     def __init__(self,model_path,preprocessor=None,num_classes = 20):

#         # load tensorrt engine =====================
#         print("TensorRT version:", trt.__version__)
#         TRT_LOGGER = trt.Logger()
#         engine_file_path = model_path
#         assert os.path.exists(engine_file_path)
#         print("Reading engine from file {}".format(engine_file_path))
#         with open(engine_file_path, "rb") as f, trt.Runtime(TRT_LOGGER) as runtime:
#             self.engine = runtime.deserialize_cuda_engine(f.read())

#         # preprocessor =============================
#         if preprocessor is not None:
#             self.preprocessor = preprocessor
#         else:
#             print("using default preprocessor for nvidia segformer pretrained cityscape")
#             self.preprocessor = self.preprocess

#         # warmup
#         self.input_shape = tuple(self.engine.get_tensor_shape("input"))
#         dummpy_images = [np.random.randint(0, 255, self.input_shape[:0:-1], dtype=np.uint8)]*self.input_shape[0]
#         self.predict(dummpy_images)
#         st = time.time()
#         for _ in range(3):
#             self.predict(dummpy_images)
#         print(f"inference time :{(time.time()-st)/3:.2f}")
#         # create a color palette, selecting a color for each class
#         self.palette = self.generate_colors(num_classes)
    
#     def generate_colors(self,num_classes):
#         hsv_colors = [(i / num_classes, 1.0, 1.0) for i in range(num_classes)]
#         rgb_colors = [colorsys.hsv_to_rgb(*color) for color in hsv_colors]
#         rgb_colors = [(int(r * 255), int(g * 255), int(b * 255)) for (r, g, b) in rgb_colors]
#         return np.array(rgb_colors).astype(np.uint8)

#     def predict(self,images):
#         """
#         input : list of bgr image

#         return : logits => numpy array (batch,h,w)
        
#         """

#         preprocessed_images = self.preprocessor(images)

#         with self.engine.create_execution_context() as context:
#             # Set input shape based on image dimensions for inference
#             tensor_name = self.engine.get_tensor_name(0) # input tensor
#             context.set_input_shape(tensor_name, self.input_shape)
#             assert context.all_binding_shapes_specified
#             # Allocate host and device bufferstrt_model.engine.get_tensor_name
#             d_input = cuda.mem_alloc(np.prod(self.input_shape) * np.dtype(np.float32).itemsize)
#             d_output = cuda.mem_alloc(np.prod(self.input_shape) * np.dtype(np.float32).itemsize)
#             context.set_tensor_address(self.engine.get_tensor_name(0), int(d_input)) # input buffer
#             context.set_tensor_address(self.engine.get_tensor_name(1), int(d_output)) #output buffer

#             cuda.memcpy_htod_async(d_input, preprocessed_images, stream) # put data to input
#             context.execute_async_v3(stream_handle=stream.handle)

#         return np.reshape(output_buffer,(self.input_shape[0],*self.input_shape[-2:]))
        
        

#     def preprocess(self,images):
#         """
#         input : list of bgr image

#         return : preprocessed batch of image => numpy array (batch,ch,h,w)
        
#         """

#         # Resize the image to match the specified input dimensions (1024x1024)
#         preprocessed_images = []

#         for image in images:
#             input_width, input_height = self.input_shape[-2:]
#             resized_image = cv2.resize(image, (input_width, input_height))
#             resized_image = cv2.cvtColor(resized_image, cv2.COLOR_BGR2RGB)

#             # Convert the image to float32 and apply color format adjustment
#             resized_image = resized_image.astype(np.float32)
#             resized_image -= np.array([123.675, 116.28, 103.53])

#             # Scale the image data by the net-scale-factor
#             net_scale_factor = 0.01735207357279195
#             resized_image *= net_scale_factor

#             # Expand dimensions to match the model input shape (3, 1024, 1024)
#             preprocessed_image = np.transpose(resized_image, (2, 0, 1))  # (H, W, C) to (C, H, W)

#             # Convert the preprocessed image to a format suitable for inference (e.g., to Tensor)
#             preprocessed_images.append(preprocessed_image)

#         return np.stack(preprocessed_images,axis=0)
    

#     def postprocess(self,datas):
#         """
#         input : logits data (segmentation result)

#         return : pil image of semantic segmentation 

#         """
#         imgs = []
#         for data in datas:
#             img = Image.fromarray(data.astype('uint8'), mode='P')
#             img.putpalette(self.palette)
#             imgs.append(img)
#         return imgs
    
#     def get_seg_overlay(self,images, segs,original_size = True):

#         if len(images) != len(segs):
#             raise Exception("number of images and seg result not equal")          

#         imgs=[]
#         for i in range(len(images)):
#             color_seg = np.zeros((segs[i].shape[0], segs[i].shape[1], 3), dtype=np.uint8) # height, width, 3
#             for label, color in enumerate(self.palette):
#                 color_seg[segs[i] == label, :] = color

#             # Show image + mask
#             if images[0].shape[:-1] != segs[0].shape:
#                 if original_size:
#                     img = images[i] * 0.5 + cv2.resize(color_seg,(images[i].shape[1],images[i].shape[0]),interpolation= cv2.INTER_LINEAR) * 0.5
#                 else:
#                     img = cv2.resize(images[i],(segs[i].shape[1],segs[i].shape[0])) * 0.5 + color_seg * 0.5
#             else:
#                 img = images[i] * 0.5 + color_seg * 0.5

#             imgs.append(img.astype(np.uint8))

#         return imgs

























# note old version predict

# with self.engine.create_execution_context() as context:
#     # Set input shape based on image dimensions for inference
#     context.set_binding_shape(self.engine.get_binding_index("input"), (1, 3, 224,224))
#     # Allocate host and device buffers
#     bindings = []
#     for binding in self.engine:
#         binding_idx = self.engine.get_binding_index(binding)
#         size = trt.volume(context.get_binding_shape(binding_idx))
#         dtype = trt.nptype(self.engine.get_binding_dtype(binding))
#         if self.engine.binding_is_input(binding):
#             input_buffer = np.ascontiguousarray(preprocessed_image)
#             input_memory = cuda.mem_alloc(preprocessed_image.nbytes)
#             bindings.append(int(input_memory))
#         else:
#             output_buffer = cuda.pagelocked_empty(size, dtype)
#             output_memory = cuda.mem_alloc(output_buffer.nbytes)
#             bindings.append(int(output_memory))

#     stream = cuda.Stream()
#     # Transfer input data to the GPU.
#     cuda.memcpy_htod_async(input_memory, input_buffer, stream)
#     # Run inference
#     context.execute_async_v2(bindings=bindings, stream_handle=stream.handle)
#     # Transfer prediction output from the GPU.
#     cuda.memcpy_dtoh_async(output_buffer, output_memory, stream)
#     # Synchronize the stream
#     stream.synchronize()



    

    # def sidewalk_palette(self):
    #     """Sidewalk palette that maps each class to RGB values."""
    #     return [
    #         [155, 155, 155],
    #         [216, 82, 24],
    #         [255, 255, 0],
    #         [125, 46, 141],
    #         [118, 171, 47],
    #         [161, 19, 46],
    #         [255, 0, 0],
    #         [0, 128, 128],
    #         [190, 190, 0],
    #         [0, 255, 0],
    #         [0, 0, 255],
    #         [170, 0, 255],
    #         [84, 84, 0],
    #         [84, 170, 0],
    #         [84, 255, 0],
    #         [170, 84, 0],
    #         [170, 170, 0],
    #         [170, 255, 0],
    #         [255, 84, 0],
    #         [255, 170, 0],
    #         [255, 255, 0],
    #         [33, 138, 200],
    #         [0, 170, 127],
    #         [0, 255, 127],
    #         [84, 0, 127],
    #         [84, 84, 127],
    #         [84, 170, 127],
    #         [84, 255, 127],
    #         [170, 0, 127],
    #         [170, 84, 127],
    #         [170, 170, 127],
    #         [170, 255, 127],
    #         [255, 0, 127],
    #         [255, 84, 127],
    #         [255, 170, 127],
    #     ]
    