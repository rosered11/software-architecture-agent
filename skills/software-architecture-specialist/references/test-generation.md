> **Auto-load:** This file is loaded when the agent enters **Test Generation** mode —
> triggered by "write tests for X", "create xunit/nunit/pytest", or when code is pasted
> with an explicit request to generate tests. Also loaded during Code Review when the
> reviewer needs to suggest concrete test cases.

# Test Generation Reference

---

## §1 — Test Strategy Decision Matrix

Choose the strategy before writing a single test. Wrong strategy = tests that lie.

| Condition | Strategy | Provider / Tool |
|-----------|----------|-----------------|
| Dependencies are injected (interfaces, not `new`) | **Unit test** | `Moq` / `NSubstitute` |
| Repositories newed inline (`new OrderRepo(_ctx)`) | **Integration test** | EF Core InMemory |
| `AsSplitQuery()` or compiled queries (`EF.CompileQuery`) present | **Integration test** | EF Core SQLite (`:memory:`) |
| External HTTP call (PSP, B2C, etc.) | **Unit test** + `HttpMessageHandler` mock | `Moq<HttpMessageHandler>` |
| Kafka producer/consumer | **Unit test** + contract test | `Confluent.Kafka.Testing` mock |
| Full flow across multiple services | **E2E / integration** | `WebApplicationFactory<T>` |

**Decision rule:**
- Any `new ConcreteClass(...)` inside the method under test → InMemory or SQLite.
- Any `await using var ctx = _factory.CreateDbContext()` → need `IDbContextFactory<T>` test double (see §3).
- Pure logic (no DB, no HTTP) → Moq is always cheaper.

---

## §2 — Branch Coverage Checklist

Every method needs tests for each branch. Run this before writing code.

### For any method
- [ ] Happy path (valid input, all data exists) → `ResultInt = 1` or expected return
- [ ] Exception path (data missing or throws) → caught error, `ResultInt = -10` or exception propagated
- [ ] Null / empty input guard → NullReferenceException or early return

### For `if (x.Equals("All"))` branch pattern
- [ ] `x = "All"` → batch path
- [ ] `x = specificId` → single-item path

### For order-reference resolution
- [ ] Reference exists → `resolvedId` ≠ `originalId`
- [ ] No reference → `resolvedId` == `originalId`

### For `IsGetRewardPromotion` flag (or any boolean toggle)
- [ ] Flag = `false` → feature skipped
- [ ] Flag = `true`, items exist → items appended
- [ ] Flag = `true`, no items → no crash, result unchanged

### For `async` + `Task.WhenAll` parallel paths
- [ ] All tasks complete within timeout (deadlock guard)
- [ ] One task throws → outer catch handles, `ResultInt = -10`

---

## §3 — EF Core InMemory Setup

### Basic pattern (use when no `AsSplitQuery` / compiled queries)

```csharp
// Unique name per test — prevents state bleed between parallel test runs
var options = new DbContextOptionsBuilder<OrderContext>()
    .UseInMemoryDatabase(Guid.NewGuid().ToString())
    .Options;

var context = new OrderContext(options);
```

### TestDbContextFactory — for IDbContextFactory<T> (see TA17)

```csharp
internal sealed class TestDbContextFactory : IDbContextFactory<OrderContext>
{
    private readonly DbContextOptions<OrderContext> _options;
    public TestDbContextFactory(DbContextOptions<OrderContext> options) => _options = options;
    public OrderContext CreateDbContext() => new OrderContext(_options);
}
```

Each `CreateDbContext()` returns a **new** `OrderContext` instance over the **same** in-memory store —
mirrors production: isolated context lifetime, shared logical database.

### When to switch to SQLite InMemory

Switch when you see any of:
- `AsSplitQuery()` throws `InvalidOperationException` at runtime
- `EF.CompileQuery(...)` static fields on the repository class
- Foreign-key constraint tests (InMemory has no FK enforcement)

```csharp
// SQLite fallback
var connection = new SqliteConnection("Filename=:memory:");
connection.Open();
var options = new DbContextOptionsBuilder<OrderContext>()
    .UseSqlite(connection)
    .Options;
using var ctx = new OrderContext(options);
ctx.Database.EnsureCreated();   // create schema
```

NuGet: `Microsoft.EntityFrameworkCore.Sqlite`

### Seed-then-assert pattern

```csharp
// Seed
context.Order.Add(new OrderModel { Id = 1, SourceOrderId = "ORD-001", IsActive = true });
context.SaveChanges();

// Act
var (result, vm) = await sut.GetSubOrderAsync("ORD-001", "SUB-001", false);

// Assert
Assert.Equal(1, result.ResultInt);
```

Always call `SaveChanges()` / `SaveChangesAsync()` after seeding — InMemory is synchronous
but the method under test may use `AsNoTracking()` which bypasses the change tracker.

---

## §4 — xUnit Test Class Structure

### Full skeleton

```csharp
public class MyMethodTests : IDisposable
{
    // One DbContext + factory per test class instance
    private readonly DbContextOptions<OrderContext> _dbOptions;
    private readonly OrderContext                   _context;
    private readonly TestDbContextFactory           _factory;
    private readonly Mock<ILogger>                  _loggerMock;
    private readonly MyService                      _sut;

    public MyMethodTests()
    {
        _dbOptions  = new DbContextOptionsBuilder<OrderContext>()
                          .UseInMemoryDatabase(Guid.NewGuid().ToString())
                          .Options;
        _context    = new OrderContext(_dbOptions);
        _factory    = new TestDbContextFactory(_dbOptions);
        _loggerMock = new Mock<ILogger>();
        _sut        = new MyService(_loggerMock.Object, _context, _factory);
    }

    public void Dispose() => _context.Dispose();

    [Fact]
    public async Task MyMethod_HappyPath_ReturnsSuccessResult() { ... }

    [Fact]
    public async Task MyMethod_MissingSubOrder_ReturnsErrorResult() { ... }

    [Theory]
    [InlineData("All")]
    [InlineData("SUB-SPECIFIC")]
    public async Task MyMethod_BothSubOrderPaths_ReturnResultIntOne(string subOrderId) { ... }
}
```

### Key xUnit APIs

| Goal | API |
|------|-----|
| Test that no exception propagates | `var ex = await Record.ExceptionAsync(() => sut.Method(...)); Assert.Null(ex);` |
| Test that specific exception throws | `await Assert.ThrowsAsync<InvalidOperationException>(() => sut.Method(...));` |
| Parameterised cases | `[Theory] + [InlineData(...)]` |
| Deadlock / timeout guard | `Task.WhenAny(workTask, Task.Delay(Timeout.Infinite, cts.Token))` → assert `Same(workTask, completed)` |
| Verify logger called | `_loggerMock.Verify(l => l.Log(LogLevel.Warning, ...), Times.Once())` |

---

## §5 — Moq Recipes for this Stack

### ILogger (most common)

```csharp
var loggerMock = new Mock<ILogger>();
// No setup needed — all Log calls succeed silently by default

// Verify a warning was logged
loggerMock.Verify(
    l => l.Log(
        LogLevel.Warning,
        It.IsAny<EventId>(),
        It.Is<It.IsAnyType>((v, _) => v.ToString()!.Contains("[PERF]")),
        null,
        It.IsAny<Func<It.IsAnyType, Exception?, string>>()),
    Times.Once());
```

### ILogger<T>

```csharp
var loggerMock = new Mock<ILogger<MyService>>();
var sut = new MyService(loggerMock.Object, context, factory);
```

### When repository IS injectable (interface-based)

```csharp
var subOrderRepoMock = new Mock<ISubOrderRepository>();
subOrderRepoMock
    .Setup(r => r.GetSubOrderMessage("ORD-001", "SUB-001"))
    .Returns(new SubOrderMessageViewModel { SourceSubOrderId = "SUB-001" });

var sut = new MyService(logger, subOrderRepoMock.Object, orderRepoMock.Object, factory);
```

### When repository is newed inline (no interface)

→ Cannot mock. Use InMemory/SQLite to control what the repository reads.
→ This is a testability smell — flag it in the Code Review with `💡 SUGGEST: Extract ISubOrderRepository interface`.

---

## §6 — Per-Technology Test Checklists

### EF Core Service (methods that call repositories)

- [ ] Seeded data matches the exact query filters (IsActive, SourceOrderId casing)
- [ ] `AsNoTracking()` on seeded context — always call `SaveChanges()` before Act
- [ ] Navigation properties loaded (Addresses, Items, Customer) — seed child collections
- [ ] `AsSplitQuery()` — use SQLite if InMemory throws
- [ ] `EF.CompileQuery` static fields — ensure test uses same provider as compile-time

### Go Handler (net/http)

```go
func TestGetSubOrder_HappyPath(t *testing.T) {
    // Use httptest.NewRecorder() + httptest.NewRequest()
    w   := httptest.NewRecorder()
    req := httptest.NewRequest(http.MethodGet, "/suborder/ORD-001/SUB-001", nil)
    handler.ServeHTTP(w, req)
    assert.Equal(t, http.StatusOK, w.Code)
}
```

Checklist:
- [ ] Test happy path with `httptest.NewRecorder`
- [ ] Test 404 when resource not found
- [ ] Test 400 for invalid input
- [ ] Mock DB layer with interface (`type SubOrderStore interface { Get(...) }`)

### Kafka Consumer

```csharp
// Use Confluent.Kafka.Testing mock or inject IConsumer<K,V>
var consumerMock = new Mock<IConsumer<string, string>>();
consumerMock.Setup(c => c.Consume(It.IsAny<CancellationToken>()))
            .Returns(new ConsumeResult<string, string> { Message = new Message<string, string> { Value = "..." } });
```

Checklist:
- [ ] Idempotency: test calling handler twice with same message → same outcome
- [ ] DLQ path: test that a processing exception routes to the dead-letter topic
- [ ] Offset commit: verify `Commit()` is called only after successful processing

---

## §7 — Test Naming Convention

Pattern: `MethodName_Condition_ExpectedOutcome`

```
GetSubOrderAsync_SpecificSubOrder_ReturnsResultIntOne
GetSubOrderAsync_SubOrderNotFound_ReturnsResultIntNegativeTen
GetSubOrderAsync_IsGetRewardPromotionFalse_NoPromotionItemsAppended
GetSubOrderAsync_OrderReferenceExists_UsesResolvedOrderIdForHeader
GetSubOrderAsync_AllSubOrders_MergesItemsFromAllSubOrders
```

Rules:
- No "Test" prefix/suffix (redundant with `[Fact]`)
- Condition describes **input state**, not implementation detail
- ExpectedOutcome is **observable** (return value, DB state, exception type)
- Avoid generic names like `GetSubOrderAsync_Works` or `GetSubOrderAsync_Test1`

---

## §8 — Output Format Template

When generating tests, always output in this order:

```
🧪 Mode: Test Generation
Method: [ClassName.MethodName]
Technology: [EF Core / Go / Kafka / ...]
Strategy: [Unit (Moq) | Integration (InMemory) | Integration (SQLite)]
Reason: [why this strategy — e.g., "repositories newed inline → InMemory required"]

Branches covered:
  ✓ [branch 1 description]
  ✓ [branch 2 description]
  ...

NuGet packages required:
  [list]

--- TEST FILE ---
[full compilable file]

--- TODO MARKERS ---
[list of class/namespace substitutions the user must make]
```
