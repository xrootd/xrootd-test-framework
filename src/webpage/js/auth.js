$(function () {
    $('#askpass').submit(function() {
        postdata = {
                    password:    $('#password').val(), 
        			testsuite:   $('#testsuite').val(),
        			cluster:     $('#cluster').val(),
        			type:        $('#type').val()
        		   };
        
        $.post('auth', postdata, function(data) {
            if (data == 'Password OK') {
                window.location.href = $('input#location').val();
            } else {
                $('.error-message').html(data)
                $('.error').show()
                $('#password').val('')
            }
        });
        return false;
    });
});
