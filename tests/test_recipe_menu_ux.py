"""Recipe Studio menu display and state-aware navigation."""
from __future__ import annotations
import tempfile
import unittest
from runtime.charge.programs.recipe_catalog import RecipeCatalog
from runtime.charge.programs.recipe_library import RecipeLibrary
from runtime.charge.programs.native_recipe_draft_library import NativeRecipeDraftLibrary
from runtime.ui.telegram.recipes import install_recipe_catalog_commands
from runtime.ui.telegram.recipe_buttons import recipe_history_markup
from test_recipe_real_callback_chain import _App, _Call

def controls(call):
    return [b.callback_data for _, k in call.message.sent for row in k['reply_markup'].inline_keyboard for b in row]

class RecipeMenuUXTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.catalog=RecipeCatalog(RecipeLibrary(self.tmp.name+'/steps',max_voltage_v=15.5,max_current_a=7.2))
        self.native=NativeRecipeDraftLibrary(self.tmp.name+'/native_recipe_drafts')
        app=_App()
        install_recipe_catalog_commands(app,catalog=self.catalog,native_drafts=self.native)
        self.handlers={h.callback.__name__:h.callback for h in app.router.callback_query.handlers}
    def step(self,version,voltage=14.4):
        self.catalog.library.save({'id':'project','version':version,'steps':[{'action':'set','params':{'voltage_v':voltage,'current_a':1.5},'until':{'current_lte':0.2}},{'action':'off','params':{},'until':{'after_seconds':60}},{'action':'wait','params':{},'until':{'after_seconds':120}}]})
    def draft(self,version,overrides):
        self.native.save('project',version,{'schema':1,'base_recipe_id':'native_efb_normal','execution_kind':'native_authority','overrides':overrides})
    async def test_readable_step_and_latest_only_actions(self):
        self.step(1)
        self.step(2,14.6)
        old=_Call('recipes:view:project:1')
        await self.handlers['show_recipe'](old)
        msg=old.message.sent[0][0]
        self.assertIn('Историческая версия',msg)
        self.assertIn('SET · U 14.4 В · I 1.5 А',msg)
        self.assertIn('I ≤ 0.2 А',msg)
        self.assertIn('OFF · выход выключен',msg)
        self.assertIn('WAIT · ожидание после OFF',msg)
        self.assertNotIn("{'voltage_v'",msg)
        self.assertNotIn('recipes:edit:project:1',controls(old))
        self.assertNotIn('recipes:archiveask:project',controls(old))
        latest=_Call('recipes:view:project:2')
        await self.handlers['show_recipe'](latest)
        self.assertIn('recipes:edit:project:2',controls(latest))
        self.assertIn('recipes:archiveask:project',controls(latest))
        history=[b.callback_data for row in recipe_history_markup(self.catalog,'project').inline_keyboard for b in row]
        self.assertIn('recipes:view:project:2',history)
    async def test_archived_step_view_and_direct_editor_refusal(self):
        self.step(1)
        self.catalog.archive('project')
        view=_Call('recipes:view:project:1')
        await self.handlers['show_recipe'](view)
        self.assertIn('Архив · только просмотр',view.message.sent[0][0])
        self.assertNotIn('recipes:edit:project:1',controls(view))
        edit=_Call('recipes:edit:project:1')
        await self.handlers['edit_menu'](edit)
        self.assertEqual(edit.message.sent,[])
        self.assertTrue(edit.acks[0][1]['show_alert'])
    async def test_native_compact_version_navigation(self):
        self.draft(1,{})
        self.draft(2,{'charge.main.efb_voltage_v':14.6})
        old=_Call('recipes:nd:view:project:1')
        await self.handlers['native_draft_view'](old)
        self.assertIn('историческая версия',old.message.sent[0][0].lower())
        self.assertIn('recipes:nd:view:project:2',controls(old))
        self.assertNotIn('recipes:nd:edit:project:1:0',controls(old))
        latest=_Call('recipes:nd:view:project:2')
        await self.handlers['native_draft_view'](latest)
        self.assertIn('Изменённые параметры',latest.message.sent[0][0])
        self.assertIn('14.6',latest.message.sent[0][0])
        self.assertIn('recipes:nd:edit:project:2:0',controls(latest))
        self.assertIn('recipes:nd:history:project:0',controls(latest))
        self.assertLessEqual(len(controls(latest)),4)
        self.native.archive('project')
        archived=_Call('recipes:nd:view:project:2')
        await self.handlers['native_draft_view'](archived)
        self.assertNotIn('recipes:nd:edit:project:2:0',controls(archived))
    async def test_old_step_editor_refusal(self):
        self.step(1)
        self.step(2,14.6)
        call=_Call('recipes:edit:project:1')
        await self.handlers['edit_menu'](call)
        self.assertEqual(call.message.sent,[])
        self.assertTrue(call.acks[0][1]['show_alert'])
        self.assertEqual(self.catalog.library.versions('project'),(1,2))

    async def test_native_history_pages_reach_every_immutable_version(self):
        for version in range(1, 15):
            self.draft(version, {})
        seen = set()
        for page in range(3):
            call = _Call(f'recipes:nd:history:project:{page}')
            await self.handlers['native_draft_history'](call)
            self.assertEqual(len(call.acks), 1)
            data = controls(call)
            self.assertTrue(all(len(item.encode('utf-8')) <= 64 for item in data))
            seen.update(int(item.rsplit(':', 1)[-1]) for item in data
                        if item.startswith('recipes:nd:view:'))
        self.assertEqual(seen, set(range(1, 15)))
        bad = _Call('recipes:nd:history:project:99')
        await self.handlers['native_draft_history'](bad)
        self.assertFalse(bad.message.sent)
        self.assertTrue(bad.acks[0][1]['show_alert'])

    async def test_archived_step_is_reachable_from_root_menu(self):
        self.step(1)
        from runtime.ui.telegram.recipe_buttons import catalog_markup
        self.catalog.archive('project')
        root = catalog_markup(self.catalog)
        self.assertIn('recipes:view:project:1',
                      [b.callback_data for row in root.inline_keyboard for b in row])
        labels = [b.text for row in root.inline_keyboard for b in row]
        self.assertTrue(any('project' in label and 'архив' in label for label in labels))
        self.assertIn('recipes:nd:list',
                      [b.callback_data for row in root.inline_keyboard for b in row])

    async def test_native_catalog_paging_archives_and_invalid_page(self):
        for number in range(26):
            self.native.save(f'copy_{number:02d}', 1, {
                'schema':1, 'base_recipe_id':'native_efb_normal',
                'execution_kind':'native_authority', 'overrides':{}})
        self.native.archive('copy_00')
        seen = set()
        for page in range(3):
            call = _Call(f'recipes:nd:list:{page}')
            await self.handlers['native_draft_list'](call)
            self.assertEqual(len(call.acks), 1)
            items = controls(call)
            self.assertTrue(all(len(c.encode('utf-8')) <= 64 for c in items))
            seen.update(c for c in items if c.startswith('recipes:nd:view:'))
        self.assertEqual(len(seen), 26)
        last = _Call('recipes:nd:list:2')
        await self.handlers['native_draft_list'](last)
        self.assertIn('архив', str(last.message.sent[0][1]['reply_markup']).lower())
        bad = _Call('recipes:nd:list:999')
        await self.handlers['native_draft_list'](bad)
        self.assertFalse(bad.message.sent)
        self.assertTrue(bad.acks[0][1]['show_alert'])
