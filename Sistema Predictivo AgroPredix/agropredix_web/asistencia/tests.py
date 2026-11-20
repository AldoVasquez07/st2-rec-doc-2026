from django.urls import reverse

from parcelas.tests import crear_distrito, crear_parcela
from recomendaciones.models import Recomendacion
from usuarios.base_pruebas import PruebaBase
from usuarios.models import Usuario

from .models import SolicitudAsistencia


class AsistenciaTests(PruebaBase):
    def setUp(self):
        self.usuario = self.crear_usuario()
        self.parcela = crear_parcela(self.usuario, crear_distrito())
        self.client.force_login(self.usuario)

    def enviar(self, **extra):
        datos = {'descripcion': 'Las hojas de mi papa tienen manchas oscuras.', **extra}
        return self.client.post(reverse('asistencia:nueva'), datos)

    def test_exige_sesion(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('asistencia:lista')).status_code, 302)

    def test_enviar_consulta_queda_como_enviada(self):
        r = self.enviar(parcela=self.parcela.pk)
        s = SolicitudAsistencia.objects.get()
        self.assertRedirects(r, reverse('asistencia:detalle', args=[s.pk]))
        self.assertEqual((s.usuario, s.estado, s.parcela), (self.usuario, 'enviada', self.parcela))

    def test_adjuntar_la_recomendacion_actual(self):
        rec = Recomendacion.objects.create(parcela=self.parcela, mes=11, resultado={'ranking': []})
        self.enviar(recomendacion=rec.pk)
        self.assertEqual(SolicitudAsistencia.objects.get().recomendacion, rec)

    def test_no_se_puede_adjuntar_recomendacion_de_otro(self):
        otro = self.crear_usuario(nombre='Otro', celular='955555555')
        ajena = Recomendacion.objects.create(parcela=crear_parcela(otro, self.parcela.distrito, 'Ajena'),
                                             mes=11, resultado={})
        r = self.enviar(recomendacion=ajena.pk)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(SolicitudAsistencia.objects.count(), 0)

    def test_consulta_muy_corta_se_rechaza(self):
        r = self.client.post(reverse('asistencia:nueva'), {'descripcion': 'hola'})
        self.assertContains(r, 'un poco más')
        self.assertEqual(SolicitudAsistencia.objects.count(), 0)

    def test_responder_la_marca_como_respondida_con_fecha(self):
        self.enviar()
        s = SolicitudAsistencia.objects.get()
        s.respuesta = 'Es probable que sea un hongo. Evite regar por la tarde.'
        s.save()
        s.refresh_from_db()
        self.assertEqual(s.estado, 'respondida')
        self.assertIsNotNone(s.fecha_respuesta)

    def test_la_respuesta_se_ve_en_el_historial_del_agricultor(self):
        self.enviar()
        s = SolicitudAsistencia.objects.get()
        s.respuesta = 'Evite regar por la tarde.'
        s.save()
        self.assertContains(self.client.get(reverse('asistencia:detalle', args=[s.pk])), 'Evite regar por la tarde.')
        self.assertContains(self.client.get(reverse('asistencia:lista')), 'Respondida')

    def test_estados_visibles(self):
        self.enviar()
        s = SolicitudAsistencia.objects.get()
        self.assertContains(self.client.get(reverse('asistencia:lista')), 'Enviada')
        s.estado = 'en_revision'
        s.save()
        self.assertContains(self.client.get(reverse('asistencia:lista')), 'En revisión')

    def test_no_se_ve_la_consulta_de_otro(self):
        self.enviar()
        s = SolicitudAsistencia.objects.get()
        otro = self.crear_usuario(nombre='Otro', celular='955555555')
        self.client.force_login(otro)
        self.assertEqual(self.client.get(reverse('asistencia:detalle', args=[s.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('asistencia:lista')), 'manchas')

    def test_el_especialista_responde_desde_el_admin(self):
        self.enviar()
        s = SolicitudAsistencia.objects.get()
        esp = Usuario.objects.create_superuser(correo='esp@x.pe', password='Clave-Segura-2026', nombre='Esp')
        self.client.force_login(esp)
        url = reverse('admin:asistencia_solicitudasistencia_change', args=[s.pk])
        r = self.client.post(url, {'estado': 'en_revision', 'respuesta': 'Revise el riego.'})
        self.assertEqual(r.status_code, 302)
        s.refresh_from_db()
        self.assertEqual((s.estado, s.respondida_por), ('respondida', esp))
