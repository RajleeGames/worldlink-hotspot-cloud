"""Safe server-side processing for newly uploaded business/platform logos."""
from io import BytesIO

from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageOps, UnidentifiedImageError


def normalize_logo(upload):
    """Crop transparent padding, preserve the complete mark, fit a 512px canvas.

    Large original image files are replaced before model size/dimension
    validation; originals are not persisted. Do not accept decompression bombs.
    """
    if not upload or upload is False:
        return upload
    if upload.size > 15 * 1024 * 1024:
        raise forms.ValidationError('Please choose a logo smaller than 15 MB.')
    if getattr(upload, 'content_type', '') not in ('image/png', 'image/jpeg', 'image/webp', 'image/gif'):
        raise forms.ValidationError('Only PNG, JPG, WebP and GIF images are supported.')
    try:
        upload.seek(0)
        with Image.open(upload) as original:
            if original.width * original.height > 24_000_000:
                raise forms.ValidationError('This image is too large. Use a logo under 24 megapixels.')
            image = ImageOps.exif_transpose(original)
            image.seek(0)  # A logo is static; animated uploads use the first frame.
            image.load()
            image = image.convert('RGBA')
        alpha = image.getchannel('A')
        bounds = alpha.getbbox()
        if bounds:
            image = image.crop(bounds)
        image.thumbnail((472, 472), Image.Resampling.LANCZOS)
        canvas = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
        canvas.alpha_composite(image, ((512 - image.width) // 2, (512 - image.height) // 2))
        buffer = BytesIO()
        canvas.save(buffer, format='PNG', optimize=True)
        return SimpleUploadedFile('logo.png', buffer.getvalue(), content_type='image/png')
    except forms.ValidationError:
        raise
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise forms.ValidationError('Could not process this image. Upload a valid logo file.') from exc


class LogoUploadFormMixin:
    def clean_logo(self):
        return normalize_logo(self.cleaned_data.get('logo'))
