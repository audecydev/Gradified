from django.contrib import admin
from django.urls import path, re_path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    if (settings.FRONTEND_DIST / 'assets').exists():
        urlpatterns += static('/assets/', document_root=settings.FRONTEND_DIST / 'assets')

# Serve React single page app
if (settings.FRONTEND_DIST / 'index.html').exists():
    urlpatterns += [
        re_path(r'^(?!api|admin|media|static).*$', TemplateView.as_view(template_name='index.html')),
    ]
