import gradio as gr
import torch
from diffusers import StableCascadeDecoderPipeline, StableCascadePriorPipeline

from modules import script_callbacks, infotext_utils, rng, processing
from modules.ui_components import ResizeHandleRow
import modules.images as images
from modules.shared import opts

# modules/processing.py
def create_infotext(prompt, negative_prompt, guidence_scale, prior_steps, decoder_steps, seed, width, height):
    generation_params = {
        "Model": "StableCascade",
        "Size": f"{width}x{height}",
        "Seed": seed,
        "Steps(Prior)": prior_steps,
        "Steps(Decoder)": decoder_steps,
        "CFG": guidence_scale,
        "RNG": opts.randn_source if opts.randn_source != "GPU" else None
    }

    generation_params_text = ", ".join([k if k == v else f'{k}: {infotext_utils.quote(v)}' for k, v in generation_params.items() if v is not None])

    prompt_text = prompt
    negative_prompt_text = f"\nNegative prompt: {negative_prompt}" if negative_prompt else ""

    return f"{prompt_text}{negative_prompt_text}\n{generation_params_text}".strip()

def predict(prompt, negative_prompt, width, height, guidance_scale, prior_steps, decoder_steps, seed, batch_size):
    device = "cuda"
    prior = StableCascadePriorPipeline.from_pretrained("stabilityai/stable-cascade-prior", torch_dtype=torch.bfloat16).to(device)

    fixed_seed = processing.get_fixed_seed(seed)

    prior_output = prior(
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        guidance_scale=guidance_scale,
        num_inference_steps=prior_steps,
        num_images_per_prompt=batch_size,
        generator=rng.create_generator(fixed_seed)
    )
    prior = None

    decoder = StableCascadeDecoderPipeline.from_pretrained("stabilityai/stable-cascade",  torch_dtype=torch.float16).to(device)
    decoder_output = decoder(
        image_embeddings=prior_output.image_embeddings.half(),
        prompt=prompt,
        negative_prompt=negative_prompt,
        guidance_scale=0.0,
        output_type="pil",
        num_inference_steps=decoder_steps
    ).images
    decoder = None

    for image in decoder_output:
        images.save_image(
            image,
            opts.outdir_samples or opts.outdir_txt2img_samples,
            "",
            fixed_seed,
            prompt,
            opts.samples_format,
            info=create_infotext(prompt, negative_prompt, guidance_scale, prior_steps, decoder_steps, fixed_seed, width, height)
        )

    return decoder_output

def on_ui_tabs():
    with gr.Blocks() as stable_cascade_block:
        with ResizeHandleRow():
            with gr.Column():
                prompt = gr.Textbox(label='Prompt', placeholder='Enter a prompt here...', default='')
                negative_prompt = gr.Textbox(label='Negative Prompt', placeholder='')
                width = gr.Slider(label='Width', minimum=16, maximum=4096, step=8, value=1024)
                height = gr.Slider(label='Height', minimum=16, maximum=4096, step=8, value=1024)
                guidence_scale = gr.Slider(label='CFG', minimum=1, maximum=32, step=0.5, value=4.0)
                prior_step = gr.Slider(label='Steps(Prior)', minimum=1, maximum=60, step=1, value=20)
                decoder_steps = gr.Slider(label='Steps(Decoder)', minimum=1, maximum=60, step=1, value=10)
                batch_size = gr.Slider(label='Batch Size', minimum=1, maximum=8, step=1, value=1)
                sampling_seed = gr.Number(label='Seed', value=-1, precision=0)

                generate_button = gr.Button(value="Generate")

                ctrls = [prompt, negative_prompt, width, height, guidence_scale, prior_step, decoder_steps, sampling_seed, batch_size]

            with gr.Column():
                output_gallery = gr.Gallery(label='Gallery', show_label=False, object_fit='contain',
                                            visible=True, height=1024, columns=4, type='pil')

        generate_button.click(predict, inputs=ctrls, outputs=[output_gallery])
    return [(stable_cascade_block, "StableCascade", "stable_cascade")]

script_callbacks.on_ui_tabs(on_ui_tabs)