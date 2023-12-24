
# Prototype: Cube.js multi-tenancy

This is a prototype to prepare for the implementation of Embeddable in Eyk 🔥🔥

Embeddable leverages Cube.js to power their caching layer. This is one of the strong points of Embeddable, because Cube.js is a well maintained & stable open-core project with a promising future.

### Goals of the prototype, in decreasing order of priority

1. Dynamically load destinations into the caching layer
2. Implement basic authentication flow
3. Fetch data from cube per destination dynamically
4. Load models per destination dynamically

And, of course, the prototype should be minimal in the sense that it just does what is required to reach the above goals, and nothing more.

### Prototype overview

![authentication overview](images/cube-auth.png)

- cube - caching layer, at startup unaware of the different destinations
- server - backend server, holds the different destinations and their connection details
- webapp - uses the server to list destinations, allows to select a destination, fetches data from cube for the selected destination, then shows the data in the browser
- destination1 - local postgres instance representing a datawarehouse for a user
- destination2 - local postgres instance representing a datawarehouse for another user

These are the most important files in this repo:
- `cube/cube.py` - configuration for cube, defines how to handle context gotten from Json Web Token to connect to the different destinations
- `server/main.py` - shows how to generate the jwt token that holds the context
- `webapp/App.js` - shows how to create a cube client with a jwt token and fetch data from the cube service

### Running the prototype

1. Run the prototype with docker compose
```bash
docker compose up
```

2. Go to the [http://localhost:3000](http://localhost:3000) in your browser

3. Fetch the available destinations in the backend server by hitting the `List destinations from API` buttin

4. Switch between destinations in the drop down and see how the data is fetched from Cube, that in turn connects to the different destinations

### Open topics / questions

- Is the implementation in `cube/cube.py` "optimal"?
  - How to best set up default security context in `scheduled_refresh_contexts()`?
  - How to deal with incomplete context passed in function calls, eg from default security context?
  - Should we use a separate orchestrator per tenant? `context_to_orchestrator_id()`
  - Anything missing?
- Implementation of `repository_factory()` in `cube/cube.py` to dynamically load data models based on context in jwt token
- Caching behavior configuration

### References

These pages in the documentation helped understand cube and how to configure it:
- https://cube.dev/docs/product/auth
- https://cube.dev/docs/product/auth/context
- https://cube.dev/docs/product/configuration/advanced/multitenancy (note: Embedddable works with COMPILE_CONTEXT, not query rewrite)
- https://cube.dev/docs/reference/configuration/config
