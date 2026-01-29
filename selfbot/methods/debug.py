import ast
import asyncio
import inspect


class Debug:
    async def aexec(self, code: str, kwargs: dict = {}) -> object:
        body = ast.parse(code, "exec").body
        if body and isinstance(body[-1], ast.Expr):
            body[-1] = ast.Return(value=body[-1].value)

        name = "aexec"
        node = ast.Module(
            body=[
                ast.AsyncFunctionDef(
                    name=name,
                    args=ast.arguments(
                        posonlyargs=[],
                        args=[ast.arg(arg=key) for key in kwargs],
                        vararg=None,
                        kwonlyargs=[],
                        kw_defaults=[],
                        kwarg=None,
                        defaults=[],
                    ),
                    body=body,
                    decorator_list=[],
                    returns=None,
                    type_params=[],
                )
            ],
            type_ignores=[],
        )
        ast.fix_missing_locations(node)

        temp = {}
        exec(compile(node, "<string>", "exec"), temp)

        func = await temp[name](*kwargs.values())
        if inspect.iscoroutine(func):
            return await func

        return func

    async def shell(self, cmd: str) -> str:
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await proc.communicate()
            return (stdout + stderr).decode("utf-8", errors="replace").rstrip()
        except asyncio.CancelledError:
            proc.kill()
            await proc.wait()
            raise
