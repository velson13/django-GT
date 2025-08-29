from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from .models import Client
from .forms import ClientForm

# List all clients
@login_required
def clients_list(request):
    clients = Client.objects.all().order_by('ime')
    return render(request, 'clients_list.html', {'clients': clients})

# View one client (optional detail page)
@login_required
def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)
    return render(request, 'client_detail.html', {'client': client})

# Create new client
@login_required
def client_add(request):
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("clients")
    else:
        form = ClientForm()
    return render(request, 'client_form.html', {'form': form})

# Edit existing client
@login_required
def client_edit(request, pk):
    # 1) Fetch the client or return 404 if not found
    client = get_object_or_404(Client, pk=pk)

    # 2) If the user submitted the form (POST), bind POST data to the form
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)  # instance=client -> update, not create
        if form.is_valid():
            form.save()            # 3) Save changes to the database
            return redirect("clients")  # 4) Go back to the list
    else:
        # 5) If GET, pre-fill the form with current client data
        form = ClientForm(instance=client)

    # 6) Render the same template as "Add", but tell it we are in edit mode
    return render(request, 'client_form.html', {
        'form': form,
        'edit_mode': True,
        'client': client,
    })

@login_required
def delete_client(request, client_id):
    client = get_object_or_404(Client, id=client_id)

    # # Check references (example: invoices and jobs reference clients by FK)
    # has_invoices = Invoice.objects.filter(client=client).exists()
    # has_jobs = Job.objects.filter(client=client).exists()

    # if has_invoices or has_jobs:
    #     messages.error(request, "❌ This client cannot be deleted because it is referenced in invoices or jobs.")
    #     return redirect("clients")

    # Safe to delete
    client.delete()
    messages.success(request, "✅ Client deleted successfully.")
    return redirect("clients")

@login_required
def invoices_list(request):
    return render(request, 'invoices.html')

@login_required
def jobs_list(request):
    return render(request, 'jobs.html')
